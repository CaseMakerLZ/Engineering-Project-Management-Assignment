package com.Agent.javabackend.dto.ProjectDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.time.OffsetDateTime;

/** 返回给前端的项目基本信息。 */
@Data
public class ProjectResponse {
    /** Java 为项目生成的 ID。 */
    @JsonProperty("project_id")
    private String projectId;
    /** 项目名称。 */
    private String name;
    /** 项目描述。 */
    private String description;
    /** 项目创建时间。 */
    @JsonProperty("created_at")
    private OffsetDateTime createdAt;
    /** 项目最后更新时间。 */
    @JsonProperty("updated_at")
    private OffsetDateTime updatedAt;

}
