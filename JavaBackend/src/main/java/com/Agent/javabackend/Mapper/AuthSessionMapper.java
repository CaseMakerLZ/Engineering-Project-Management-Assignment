package com.Agent.javabackend.Mapper;

import com.Agent.javabackend.entity.MessageContainer.AuthSession;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.time.OffsetDateTime;
import java.util.Optional;

/** 云端登录会话表的数据访问接口。 */
@Mapper
public interface AuthSessionMapper {
    int insert(AuthSession session);

    Optional<AuthSession> findActiveByTokenHash(
            @Param("tokenHash") String tokenHash,
            @Param("now") OffsetDateTime now);

    int revokeById(
            @Param("sessionId") String sessionId,
            @Param("revokedAt") OffsetDateTime revokedAt);
}
