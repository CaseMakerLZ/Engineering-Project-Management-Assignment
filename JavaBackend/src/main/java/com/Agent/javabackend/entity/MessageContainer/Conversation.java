package com.Agent.javabackend.entity.MessageContainer;

import lombok.Data;

import java.time.OffsetDateTime;

/** 数据库中的对话记录。 */
@Data
public class Conversation {
    /** 对话 ID。 */
    private String id;
    /** 所属项目 ID。 */
    private String projectId;
    /** 对话标题。 */
    private String title;
    /** 对话状态，目前使用 ACTIVE。 */
    private String status;
    /** 对话创建时间。 */
    private OffsetDateTime createdAt;
    /** 对话最后更新时间。 */
    private OffsetDateTime updatedAt;
}
