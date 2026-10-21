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
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;

@Service
public class ProjectServiceImpl implements ProjectService {
    private final ProjectMapper projects;
    private final String activeProfile;

    public ProjectServiceImpl(ProjectMapper projects,
                              @Value("${spring.profiles.active:local}") String activeProfile) {
        this.projects = projects;
        this.activeProfile = activeProfile;
    }

    @Override
    public ProjectResponse create(CreateProjectRequest request) {
        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        Project project = new Project();
        project.setId(UUID.randomUUID().toString());
        project.setName(request.getName());
        project.setDescription(request.getDescription());
        if ("local".equalsIgnoreCase(activeProfile)) {
            if (request.getLocalPath() == null || request.getLocalPath().isBlank()) {
                throw new BaseException(ErrorCode.INVALID_ARGUMENT, "本地项目目录不得为空");
            }
            Path localPath = Path.of(request.getLocalPath()).toAbsolutePath().normalize();
            if (!Files.isDirectory(localPath)) {
                throw new BaseException(ErrorCode.INVALID_ARGUMENT, "项目目录不存在或不是目录");
            }
            project.setLocalPath(localPath.toString());
        }
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
        response.setLocalPath(project.getLocalPath());
        response.setCreatedAt(project.getCreatedAt());
        response.setUpdatedAt(project.getUpdatedAt());
        return response;
    }
}
