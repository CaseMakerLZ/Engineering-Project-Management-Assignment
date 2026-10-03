package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.dto.ProjectDTO.ProjectResponse;

public interface ProjectService {
    ProjectResponse create(CreateProjectRequest request);
    ProjectResponse get(String projectId);

    /** 只检查项目是否存在；不存在时抛出业务异常。 */
    void requireExists(String projectId);
}
