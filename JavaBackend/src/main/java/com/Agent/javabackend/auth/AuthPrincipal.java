package com.Agent.javabackend.auth;

import com.Agent.javabackend.entity.MessageContainer.User;

import java.time.OffsetDateTime;

/** 已通过服务端令牌校验的当前用户及其会话。 */
public record AuthPrincipal(User user, String sessionId, OffsetDateTime expiresAt) {
    public static final String REQUEST_ATTRIBUTE = "authenticatedPrincipal";

    /** 兼容只关心用户和会话的调用方；实时连接再按需读取 expiresAt。 */
    public AuthPrincipal(User user, String sessionId) {
        this(user, sessionId, null);
    }
}
