package com.Agent.javabackend.Service;

import com.Agent.javabackend.Config.LocalDirectoryProperties;
import com.Agent.javabackend.dto.LocalDirectoryDTO.CreateLocalDirectoryResponse;
import com.Agent.javabackend.dto.LocalDirectoryDTO.LocalDirectoryBrowseResponse;
import com.Agent.javabackend.dto.LocalDirectoryDTO.LocalDirectoryEntry;
import com.Agent.javabackend.dto.LocalDirectoryDTO.LocalDirectoryRoot;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.stereotype.Service;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.DirectoryIteratorException;
import java.nio.file.DirectoryStream;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

/**
 * local 模式的本机目录浏览、创建与最终绑定校验。
 *
 * 所有入口共用同一套规则：只接受服务端配置的根位置、只接受相对路径、
 * 逐段拒绝符号链接/越界解析、限制扫描数量与时间，并由服务端签发分页游标。
 */
@Service
public class LocalDirectoryService {
    private static final int DEFAULT_PAGE_SIZE = 100;
    private static final int MAX_PATH_LENGTH = 1024;
    private static final int MAX_NAME_LENGTH = 255;
    private static final int MAX_CURSOR_LENGTH = 4096;
    private static final Pattern DRIVE_PREFIX = Pattern.compile("^[A-Za-z]:.*");
    private static final Set<String> WINDOWS_RESERVED = Set.of(
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9");

    private final LocalDirectoryProperties properties;
    private final List<Root> roots;
    private final byte[] cursorSecret;

    public LocalDirectoryService(LocalDirectoryProperties properties) {
        this.properties = properties;
        this.roots = buildRoots(properties.getRoots());
        this.cursorSecret = resolveCursorSecret(properties.getCursorSecret());
    }

    public LocalDirectoryBrowseResponse browse(String rootId, String rawPath,
                                               int pageSize, String cursor) {
        if (rootId == null || rootId.isBlank()) {
            if (rawPath != null && !rawPath.isEmpty()) {
                throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
            }
            if (cursor != null && !cursor.isBlank()) {
                throw new BaseException(ErrorCode.INVALID_ARGUMENT, "根入口请求不接受 cursor");
            }
            return rootsResponse();
        }

        int size = validPageSize(pageSize);
        Root root = requireRoot(rootId);
        String relativePath = normalizeRelativePath(rawPath, true);
        Path directory = resolveExistingDirectory(root, relativePath);
        int offset = decodeCursor(cursor, rootId, relativePath);
        List<LocalDirectoryEntry> all = listDirectories(root, directory, relativePath);
        if (offset > all.size()) {
            throw new BaseException(ErrorCode.INVALID_ARGUMENT, "cursor 已失效，请重新浏览");
        }
        int end = Math.min(all.size(), offset + size);
        String nextCursor = end < all.size()
                ? encodeCursor(rootId, relativePath, end) : null;

        LocalDirectoryBrowseResponse response = new LocalDirectoryBrowseResponse();
        response.setRoots(List.of());
        response.setRootId(rootId);
        response.setPath(relativePath);
        response.setAbsolutePath(displayPath(directory));
        response.setEntries(List.copyOf(all.subList(offset, end)));
        response.setNextCursor(nextCursor);
        return response;
    }

    private LocalDirectoryBrowseResponse rootsResponse() {
        LocalDirectoryBrowseResponse response = new LocalDirectoryBrowseResponse();
        response.setRoots(roots.stream()
                .map(root -> new LocalDirectoryRoot(root.rootId(), root.name()))
                .toList());
        response.setEntries(List.of());
        return response;
    }

    public CreateLocalDirectoryResponse create(String rootId, String parentPath, String name) {
        Root root = requireRoot(rootId);
        String parentRelativePath = normalizeRelativePath(parentPath, true);
        Path parent = resolveExistingDirectory(root, parentRelativePath);
        String safeName = validateNewDirectoryName(name);
        if (!Files.isReadable(parent) || !Files.isWritable(parent)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
        }

        Path target = parent.resolve(safeName).normalize();
        if (!target.startsWith(parent)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        try {
            // createDirectory 只建一层，同名时由文件系统原子拒绝，不会覆盖已有内容。
            Files.createDirectory(target);
        } catch (FileAlreadyExistsException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ALREADY_EXISTS, exception);
        } catch (AccessDeniedException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED, exception);
        } catch (IOException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE, exception);
        }

        Path canonicalTarget;
        try {
            canonicalTarget = target.toRealPath();
        } catch (IOException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE, exception);
        }
        if (!canonicalTarget.startsWith(rootReal(root))) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
        }
        String relativePath = parentRelativePath.isEmpty()
                ? safeName : parentRelativePath + "/" + safeName;
        return new CreateLocalDirectoryResponse(
                rootId, relativePath, displayPath(canonicalTarget));
    }

    /**
     * 保存 project.local_path 前的最终检查。
     *
     * 这里重新解析真实路径，不能只相信浏览接口返回的字符串；伪造 POST
     * 也无法绕过允许根、符号链接/越界和读写权限检查。
     */
    public String validateBindableDirectory(String rawAbsolutePath) {
        if (rawAbsolutePath == null || rawAbsolutePath.isBlank()) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        Path given;
        try {
            given = Path.of(rawAbsolutePath);
        } catch (InvalidPathException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID, exception);
        }
        if (!given.isAbsolute()) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        Path normalized = given.toAbsolutePath().normalize();
        if (!Files.exists(normalized, LinkOption.NOFOLLOW_LINKS)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_NOT_FOUND);
        }
        if (Files.isSymbolicLink(normalized)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
        }
        if (!Files.isDirectory(normalized)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }

        for (Root root : roots) {
            Path rootReal = rootRealIfAvailable(root);
            if (rootReal == null || !normalized.startsWith(rootReal)) {
                continue;
            }
            String relativePath = rootReal.relativize(normalized).toString()
                    .replace('\\', '/');
            Path resolved = resolveExistingDirectory(root, relativePath);
            if (!Files.isReadable(resolved) || !Files.isWritable(resolved)) {
                throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
            }
            return displayPath(resolved);
        }
        throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
    }

    private static List<Root> buildRoots(List<LocalDirectoryProperties.Root> configured) {
        if (configured == null || configured.isEmpty()) {
            return List.of();
        }
        List<Root> result = new ArrayList<>();
        Set<String> rootIds = new HashSet<>();
        for (LocalDirectoryProperties.Root candidate : configured) {
            if (candidate == null || candidate.getPath() == null || candidate.getPath().isBlank()) {
                continue;
            }
            if (candidate.getRootId() == null || candidate.getRootId().isBlank()
                    || candidate.getName() == null || candidate.getName().isBlank()) {
                throw new IllegalArgumentException("local-directory.roots 的 root-id 和 name 不得为空");
            }
            if (!rootIds.add(candidate.getRootId())) {
                throw new IllegalArgumentException(
                        "local-directory.roots 存在重复 root-id: " + candidate.getRootId());
            }
            Path path;
            try {
                path = Path.of(candidate.getPath()).toAbsolutePath().normalize();
            } catch (InvalidPathException exception) {
                throw new IllegalArgumentException(
                        "local-directory.roots 路径不合法: " + candidate.getRootId(), exception);
            }
            result.add(new Root(candidate.getRootId(), candidate.getName(), path));
        }
        return List.copyOf(result);
    }

    private static byte[] resolveCursorSecret(String configured) {
        if (configured != null && !configured.isBlank()) {
            return configured.getBytes(StandardCharsets.UTF_8);
        }
        byte[] generated = new byte[32];
        new SecureRandom().nextBytes(generated);
        return generated;
    }

    private int validPageSize(int pageSize) {
        // 文档约定每页最多 200；配置只能收窄，不能放大这个硬上限。
        int max = Math.min(200, Math.max(1, properties.getMaxPageSize()));
        if (pageSize < 1 || pageSize > max) {
            throw new BaseException(ErrorCode.INVALID_ARGUMENT,
                    "page_size 必须在 1 到 " + max + " 之间");
        }
        return pageSize;
    }

    private Root requireRoot(String rootId) {
        if (rootId == null || rootId.isBlank()) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_NOT_FOUND);
        }
        return roots.stream()
                .filter(root -> root.rootId().equals(rootId))
                .findFirst()
                .orElseThrow(() -> new BaseException(ErrorCode.LOCAL_DIRECTORY_NOT_FOUND));
    }

    static String normalizeRelativePath(String rawPath, boolean allowRoot) {
        String path = rawPath == null ? "" : rawPath;
        if (path.isEmpty()) {
            if (allowRoot) {
                return "";
            }
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        if (path.length() > MAX_PATH_LENGTH || path.startsWith("/")
                || path.indexOf('\\') >= 0 || DRIVE_PREFIX.matcher(path).matches()) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        String[] segments = path.split("/", -1);
        for (String segment : segments) {
            if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)
                    || segment.codePointCount(0, segment.length()) > MAX_NAME_LENGTH) {
                throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
            }
            for (int index = 0; index < segment.length(); index++) {
                char value = segment.charAt(index);
                if (value < 0x20 || value == 0x7f || isWindowsInvalidChar(value)) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
                }
            }
        }
        return String.join("/", segments);
    }

    private static String validateNewDirectoryName(String name) {
        if (name == null || name.isBlank() || !name.equals(name.trim())
                || name.codePointCount(0, name.length()) > MAX_NAME_LENGTH
                || ".".equals(name) || "..".equals(name)
                || name.endsWith(".") || name.endsWith(" ")) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        for (int index = 0; index < name.length(); index++) {
            char value = name.charAt(index);
            if (value < 0x20 || value == 0x7f || isWindowsInvalidChar(value)) {
                throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
            }
        }
        int dot = name.indexOf('.');
        String baseName = (dot < 0 ? name : name.substring(0, dot)).toUpperCase(Locale.ROOT);
        if (WINDOWS_RESERVED.contains(baseName)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        return name;
    }

    private static boolean isWindowsInvalidChar(char value) {
        return value == '/' || value == '\\' || value == ':' || value == '*' || value == '?' || value == '"'
                || value == '<' || value == '>' || value == '|';
    }

    /**
     * 从根位置逐段解析相对路径。
     *
     * 每一段都检查 NOFOLLOW 存在性、符号链接和真实路径是否仍在根内，
     * 因此 Windows junction 或符号链接即使字符串前缀合法也不能越界。
     */
    private Path resolveExistingDirectory(Root root, String relativePath) {
        Path rootReal = rootReal(root);
        if (!Files.isReadable(rootReal)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
        }
        Path current = rootReal;
        if (!relativePath.isEmpty()) {
            for (String segment : relativePath.split("/")) {
                current = current.resolve(segment);
                if (!Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_NOT_FOUND);
                }
                if (Files.isSymbolicLink(current)) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
                }
                Path real;
                try {
                    real = current.toRealPath();
                } catch (NoSuchFileException exception) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_NOT_FOUND, exception);
                } catch (AccessDeniedException exception) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED, exception);
                } catch (IOException exception) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE, exception);
                }
                if (!real.startsWith(rootReal)) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
                }
                current = real;
            }
        }
        if (!Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_PATH_INVALID);
        }
        if (!Files.isReadable(current)) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED);
        }
        return current;
    }

    private List<LocalDirectoryEntry> listDirectories(
            Root root, Path directory, String relativePath) {
        Path rootReal = rootReal(root);
        int maxScan = Math.max(1, properties.getMaxScanEntries());
        long timeoutNanos = TimeUnit.MILLISECONDS.toNanos(
                Math.max(1, properties.getScanTimeoutMs()));
        long deadline = System.nanoTime() + timeoutNanos;
        int scanned = 0;
        List<LocalDirectoryEntry> entries = new ArrayList<>();

        try (DirectoryStream<Path> stream = Files.newDirectoryStream(directory)) {
            for (Path child : stream) {
                if (++scanned > maxScan) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE,
                            "目录项过多，请缩小浏览范围");
                }
                if ((scanned & 0x7f) == 0 && System.nanoTime() - deadline > 0) {
                    throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE,
                            "目录扫描超时，请稍后重试");
                }
                if (Files.isSymbolicLink(child)
                        || !Files.isDirectory(child, LinkOption.NOFOLLOW_LINKS)
                        || !Files.isReadable(child)) {
                    continue;
                }
                Path realChild;
                try {
                    realChild = child.toRealPath();
                } catch (IOException exception) {
                    continue;
                }
                if (!realChild.startsWith(rootReal)) {
                    continue;
                }
                String name = child.getFileName().toString();
                String entryPath = relativePath.isEmpty()
                        ? name : relativePath + "/" + name;
                entries.add(new LocalDirectoryEntry(name, entryPath));
            }
        } catch (DirectoryIteratorException exception) {
            if (exception.getCause() instanceof AccessDeniedException) {
                throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED, exception);
            }
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE, exception);
        } catch (IOException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE, exception);
        }

        entries.sort(Comparator
                .comparing(LocalDirectoryEntry::getName, String.CASE_INSENSITIVE_ORDER)
                .thenComparing(LocalDirectoryEntry::getName));
        return entries;
    }

    private Path rootReal(Root root) {
        Path real = rootRealIfAvailable(root);
        if (real == null) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_NOT_FOUND);
        }
        return real;
    }

    private Path rootRealIfAvailable(Root root) {
        try {
            Path real = root.path().toRealPath();
            return Files.isDirectory(real, LinkOption.NOFOLLOW_LINKS) ? real : null;
        } catch (NoSuchFileException exception) {
            return null;
        } catch (AccessDeniedException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_ACCESS_DENIED, exception);
        } catch (IOException exception) {
            throw new BaseException(ErrorCode.LOCAL_DIRECTORY_UNAVAILABLE, exception);
        }
    }

    private static String displayPath(Path path) {
        return path.toAbsolutePath().normalize().toString().replace('\\', '/');
    }

    private String encodeCursor(String rootId, String relativePath, int offset) {
        String payload = rootId + "\n" + relativePath + "\n" + offset;
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
        return encoded + "." + sign(encoded);
    }

    private int decodeCursor(String cursor, String rootId, String relativePath) {
        if (cursor == null || cursor.isBlank()) {
            return 0;
        }
        if (cursor.length() > MAX_CURSOR_LENGTH) {
            throw new BaseException(ErrorCode.INVALID_ARGUMENT, "cursor 长度不合法");
        }
        try {
            int separator = cursor.indexOf('.');
            if (separator <= 0 || separator == cursor.length() - 1) {
                throw new IllegalArgumentException("cursor 格式错误");
            }
            String encoded = cursor.substring(0, separator);
            String signature = cursor.substring(separator + 1);
            byte[] expected = sign(encoded).getBytes(StandardCharsets.UTF_8);
            if (!MessageDigest.isEqual(expected, signature.getBytes(StandardCharsets.UTF_8))) {
                throw new IllegalArgumentException("cursor 签名错误");
            }
            String payload = new String(Base64.getUrlDecoder().decode(encoded),
                    StandardCharsets.UTF_8);
            String[] parts = payload.split("\n", -1);
            if (parts.length != 3 || !rootId.equals(parts[0])
                    || !relativePath.equals(parts[1])) {
                throw new IllegalArgumentException("cursor 与当前目录不匹配");
            }
            int offset = Integer.parseInt(parts[2]);
            if (offset < 0) {
                throw new IllegalArgumentException("cursor 偏移非法");
            }
            return offset;
        } catch (RuntimeException exception) {
            throw new BaseException(ErrorCode.INVALID_ARGUMENT, "cursor 已失效，请重新浏览", exception);
        }
    }

    private String sign(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(cursorSecret, "HmacSHA256"));
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException("无法签发本地目录游标", exception);
        }
    }

    private record Root(String rootId, String name, Path path) {
    }
}
