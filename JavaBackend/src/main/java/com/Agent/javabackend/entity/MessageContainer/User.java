package com.Agent.javabackend.entity.MessageContainer;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.Getter;
import lombok.Setter;

import java.time.OffsetDateTime;

/** 云端 MySQL 中的用户记录；本地模式不使用。 */
@Getter
@Setter
public class User {
    /** 云端用户的稳定标识，与 project.owner_id 对应。 */
    private String userId;
    /** 登录名；唯一性由数据库约束保证。 */
    private String username;
    /** 只保存密码哈希，不保存明文；接口响应不得返回此字段。 */
    @JsonIgnore
    private String passwordHash;
    /** ACTIVE 或 DISABLED；禁用用户不得通过登录或令牌鉴权。 */
    private String status;
    /** 最近一次成功登录时间；从未登录时为空。 */
    private OffsetDateTime lastLoginAt;
    /** 用户创建时间。 */
    private OffsetDateTime createdAt;
    /** 用户资料最后更新时间。 */
    private OffsetDateTime updatedAt;
}
