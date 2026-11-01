package com.Agent.javabackend.dto.ProjectDTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

/** Python 内部工作区准备接口的返回结果。 */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ProjectWorkspaceResponse {
    /** Python 已准备完成的项目 ID。 */
    @JsonProperty("project_id")
    private String projectId;

    /** 工作区是否已经可用。 */
    private Boolean ready;
}
