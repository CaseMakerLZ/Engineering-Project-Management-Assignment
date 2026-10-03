package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Service.ProjectService;
import com.Agent.javabackend.Mapper.ProjectMapper;
import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.dto.ProjectDTO.ProjectResponse;
import com.Agent.javabackend.entity.MessageContainer.Project;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;

@Service
public class ProjectServiceImpl implements ProjectService {
    private final ProjectMapper projects;

    public ProjectServiceImpl(ProjectMapper projects) {
        this.projects = projects;
    }

    @Override
    public ProjectResponse create(CreateProjectRequest request) {
        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        Project project = new Project();
        project.setId(UUID.randomUUID().toString());
        project.setName(request.getName());
        project.setDescription(request.getDescription());
        project.setCreatedAt(now);
        project.setUpdatedAt(now);
        projects.insert(project);
        return toResponse(project);
    }

    @Override
    public ProjectResponse get(String projectId) {
        Project project = projects.findById(projectId)
                .orElseThrow(() -> new BaseException(ErrorCode.PROJECT_NOT_FOUND));
        return toResponse(project);
    }

    @Override
    public void requireExists(String projectId) {
        if (projects.findById(projectId).isEmpty()) {
            throw new BaseException(ErrorCode.PROJECT_NOT_FOUND);
        }
    }

    // 项目实体用于内部存储，响应 DTO 只包含接口需要返回的字段。
    private ProjectResponse toResponse(Project project) {
        ProjectResponse response = new ProjectResponse();
        response.setProjectId(project.getId());
        response.setName(project.getName());
        response.setDescription(project.getDescription());
        response.setCreatedAt(project.getCreatedAt());
        response.setUpdatedAt(project.getUpdatedAt());
        return response;
    }
}
