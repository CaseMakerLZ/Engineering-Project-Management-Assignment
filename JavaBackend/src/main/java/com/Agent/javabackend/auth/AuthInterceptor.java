package com.Agent.javabackend.auth;

import com.Agent.javabackend.Service.AuthService;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/** 云端模式下统一校验受保护接口的 Bearer 令牌。 */
@Profile("cloud")
@Component
public class AuthInterceptor implements HandlerInterceptor {
    private final AuthService authService;

    public AuthInterceptor(AuthService authService) {
        this.authService = authService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }

        AuthPrincipal principal = authService.authenticate(extractBearerToken(request));
        request.setAttribute(AuthPrincipal.REQUEST_ATTRIBUTE, principal);
        return true;
    }

    private String extractBearerToken(HttpServletRequest request) {
        String authorization = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (authorization == null) {
            throw new BaseException(ErrorCode.AUTH_TOKEN_INVALID);
        }

        String prefix = "Bearer ";
        if (authorization.length() <= prefix.length()
                || !authorization.regionMatches(true, 0, prefix, 0, prefix.length())) {
            throw new BaseException(ErrorCode.AUTH_TOKEN_INVALID);
        }

        String token = authorization.substring(prefix.length()).trim();
        if (token.isEmpty() || token.chars().anyMatch(Character::isWhitespace)) {
            throw new BaseException(ErrorCode.AUTH_TOKEN_INVALID);
        }
        return token;
    }
}
