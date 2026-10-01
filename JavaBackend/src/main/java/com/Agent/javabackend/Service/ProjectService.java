package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.dto.ProjectDTO.ProjectResponse;

public interface ProjectService {
    ProjectResponse create(CreateProjectRequest request);
    ProjectResponse get(String projectId);
}
