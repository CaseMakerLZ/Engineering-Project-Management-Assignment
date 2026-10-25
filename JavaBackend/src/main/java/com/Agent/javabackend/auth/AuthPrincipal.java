package com.Agent.javabackend.auth;

import com.Agent.javabackend.entity.MessageContainer.User;

/** 已通过服务端令牌校验的当前用户及其会话。 */
public record AuthPrincipal(User user, String sessionId) {
    public static final String REQUEST_ATTRIBUTE = "authenticatedPrincipal";
}
