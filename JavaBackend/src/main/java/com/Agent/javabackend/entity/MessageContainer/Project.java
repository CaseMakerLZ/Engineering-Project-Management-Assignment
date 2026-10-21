package com.Agent.javabackend.entity.MessageContainer;

import lombok.Data;

import java.time.OffsetDateTime;

/** 数据库中的项目记录。 */
@Data
public class Project {
    /** 项目 ID。 */
    private String id;
    /** 项目名称。 */
    private String name;
    /** 项目描述。 */
    private String description;
    /** 本地模式下绑定的真实项目目录；云端模式不使用。 */
    private String localPath;
    /** 项目所有者 ID，用户功能完成后使用。 */
    private String ownerId;
    /** 项目创建时间。 */
    private OffsetDateTime createdAt;
    /** 项目最后更新时间。 */
    private OffsetDateTime updatedAt;
}
