package com.Agent.javabackend.entity.MessageContainer;

import lombok.Data;

import java.time.OffsetDateTime;

@Data
public class Project {
    private String id;
    private String name;
    private String description;
    private String ownerId;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
