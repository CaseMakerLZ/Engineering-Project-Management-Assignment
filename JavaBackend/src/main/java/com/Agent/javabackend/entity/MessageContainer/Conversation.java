package com.Agent.javabackend.entity.MessageContainer;

import lombok.Data;

import java.time.OffsetDateTime;

@Data
public class Conversation {
    private String id;
    private String projectId;
    private String title;
    private String status;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
