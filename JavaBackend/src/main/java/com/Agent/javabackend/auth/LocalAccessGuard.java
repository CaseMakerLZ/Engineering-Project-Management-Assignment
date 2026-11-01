package com.Agent.javabackend.auth;

import com.Agent.javabackend.Config.LocalDirectoryProperties;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

import java.nio.charset.StandardCharsets;
import java.net.URI;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * local 模式不登录，但不能因此允许任意网页浏览本机目录。
 *
 * 只接受可信 Host 和配置的 Origin；缺少 Origin 的请求必须携带本机凭据。
 * 设置 access-token 后，所有实际请求也都要携带该凭据。
 */
public class LocalAccessGuard implements HandlerInterceptor {
    public static final String TOKEN_HEADER = "X-Local-Access-Token";

    private final Set<String> trustedHosts = new HashSet<>();
    private final Set<String> allowedOrigins = new HashSet<>();
    private final String accessToken;

    public LocalAccessGuard(LocalDirectoryProperties properties) {
        for (String host : properties.getTrustedHosts()) {
            if (host != null && !host.isBlank()) {
                trustedHosts.add(normalizeHost(host));
            }
        }
        for (String origin : properties.getAllowedOrigins()) {
            if (origin != null && !origin.isBlank()) {
                allowedOrigins.add(normalizeOrigin(origin));
            }
        }
        this.accessToken = properties.getAccessToken() == null
                ? "" : properties.getAccessToken();
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response,
                             Object handler) {
        if (!isTrustedHost(request.getHeader("Host"))) {
            throw new BaseException(ErrorCode.LOCAL_ACCESS_DENIED);
        }

        String origin = request.getHeader("Origin");
        boolean hasOrigin = origin != null && !origin.isBlank();
        if (hasOrigin && !allowedOrigins.contains(normalizeOrigin(origin))) {
            throw new BaseException(ErrorCode.LOCAL_ACCESS_DENIED);
        }
        // 浏览器同源 GET 通常不发送 Origin；仅接受可信 Referer 与 same-origin 标记同时存在的只读请求。
        // 补充原规则：无浏览器来源证据的请求仍必须持有本机凭据；配置凭据后仍由下方强制校验。
        if (!hasOrigin && !trustedSameOriginRead(request)
                && !validToken(request.getHeader(TOKEN_HEADER))) {
            // 没有 Origin 的请求不能无条件信任；必须证明自己持有本机凭据。
            throw new BaseException(ErrorCode.LOCAL_ACCESS_DENIED);
        }

        boolean preflight = "OPTIONS".equalsIgnoreCase(request.getMethod());
        if (!preflight && !accessToken.isBlank()
                && !validToken(request.getHeader(TOKEN_HEADER))) {
            throw new BaseException(ErrorCode.LOCAL_ACCESS_DENIED);
        }
        return true;
    }

    private boolean trustedSameOriginRead(HttpServletRequest request) {
        String method = request.getMethod();
        if (!("GET".equalsIgnoreCase(method) || "HEAD".equalsIgnoreCase(method))
                || !"same-origin".equalsIgnoreCase(request.getHeader("Sec-Fetch-Site"))) {
            return false;
        }
        String referer = request.getHeader("Referer");
        if (referer == null || referer.isBlank()) {
            return false;
        }
        try {
            URI uri = URI.create(referer);
            String scheme = uri.getScheme();
            if (!("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme))
                    || uri.getHost() == null || uri.getRawUserInfo() != null) {
                return false;
            }
            String origin = scheme + "://" + uri.getRawAuthority();
            return allowedOrigins.contains(normalizeOrigin(origin));
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private boolean validToken(String provided) {
        if (accessToken.isBlank() || provided == null) {
            return false;
        }
        return MessageDigest.isEqual(
                provided.getBytes(StandardCharsets.UTF_8),
                accessToken.getBytes(StandardCharsets.UTF_8));
    }

    private boolean isTrustedHost(String header) {
        if (header == null || header.isBlank()) {
            return false;
        }
        String host = header.trim().toLowerCase(Locale.ROOT).replaceAll("/+$", "");
        if (host.startsWith("[")) {
            int end = host.indexOf(']');
            if (end < 0) {
                return false;
            }
            host = host.substring(1, end);
        } else {
            int colon = host.lastIndexOf(':');
            if (colon >= 0) {
                if (host.indexOf(':') != colon) {
                    return false;
                }
                host = host.substring(0, colon);
            }
        }
        if (host.endsWith(".")) {
            host = host.substring(0, host.length() - 1);
        }
        return !host.isBlank() && trustedHosts.contains(host);
    }

    private static String normalizeHost(String value) {
        String host = value.trim().toLowerCase(Locale.ROOT);
        if (host.startsWith("[") && host.endsWith("]")) {
            host = host.substring(1, host.length() - 1);
        }
        return host;
    }

    private static String normalizeOrigin(String value) {
        String origin = value.trim().toLowerCase(Locale.ROOT);
        while (origin.endsWith("/")) {
            origin = origin.substring(0, origin.length() - 1);
        }
        return origin;
    }
}
