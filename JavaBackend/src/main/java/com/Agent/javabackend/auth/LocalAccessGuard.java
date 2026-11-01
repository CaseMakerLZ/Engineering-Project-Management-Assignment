package com.Agent.javabackend.auth;

import com.Agent.javabackend.Config.LocalDirectoryProperties;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

import java.nio.charset.StandardCharsets;
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
        if (!hasOrigin && !validToken(request.getHeader(TOKEN_HEADER))) {
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
