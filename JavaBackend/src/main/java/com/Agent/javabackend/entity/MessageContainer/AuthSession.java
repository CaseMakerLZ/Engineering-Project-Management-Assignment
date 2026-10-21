package com.Agent.javabackend.entity.MessageContainer;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.Getter;
import lombok.Setter;

import java.time.OffsetDateTime;

/** 云端 MySQL 中的登录会话记录；不保存原始令牌。 */
@Getter
@Setter
public class AuthSession {
    /** 服务端生成的会话 ID。 */
    private String sessionId;
    /** 会话所属用户。 */
    private String userId;
    /** 原始令牌的 SHA-256 十六进制摘要，不向客户端返回。 */
    @JsonIgnore
    private String tokenHash;
    /** 令牌到期时间。 */
    private OffsetDateTime expiresAt;
    /** 注销时间；未注销时为空。 */
    private OffsetDateTime revokedAt;
    /** 会话创建时间。 */
    private OffsetDateTime createdAt;
}
