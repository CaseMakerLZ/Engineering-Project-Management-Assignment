package com.Agent.javabackend.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.OffsetDateTime;

/** Python Agent Service 返回的一条运行消息。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class MessageResponse {
    private Integer sequence;

    @JsonProperty("message_type")
    private String messageType;

    /** Python 端允许字符串或 JSON 对象，因此暂时使用 Object 承载。 */
    private Object content;

    @JsonProperty("created_at")
    private OffsetDateTime createdAt;
}
