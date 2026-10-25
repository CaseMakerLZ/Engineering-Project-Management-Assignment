package com.Agent.javabackend.Mapper;

import com.Agent.javabackend.entity.MessageContainer.User;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.time.OffsetDateTime;
import java.util.Optional;

/** 云端用户表的数据访问接口。 */
@Mapper
public interface UserMapper {
    int insert(User user);

    Optional<User> findByUsername(@Param("username") String username);

    Optional<User> findById(@Param("userId") String userId);

    int updateLastLogin(
            @Param("userId") String userId,
            @Param("lastLoginAt") OffsetDateTime lastLoginAt);
}
