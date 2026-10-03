package com.Agent.javabackend.dto.ConversationDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.time.OffsetDateTime;

/** 返回给前端的一段对话的基本信息。 */
@Data
public class ConversationResponse {
    /** Java 为这段对话生成的 ID。 */
    @JsonProperty("conversation_id")
    private String conversationId;
    /** 这段对话所属的项目 ID。 */
    @JsonProperty("project_id")
    private String projectId;
    /** 对话标题。 */
    private String title;
    /** 对话当前是否可用。 */
    private String status;
    /** 对话创建时间。 */
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;
    /** 对话最后一次更新的时间。 */
    @JsonProperty("updated_at")
    private OffsetDateTime updatedAt;

}
