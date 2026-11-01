package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Client.PythonAgentClient;
import com.Agent.javabackend.Service.ProjectService;
import com.Agent.javabackend.Mapper.ProjectMapper;
import com.Agent.javabackend.Service.LocalDirectoryService;
import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.dto.ProjectDTO.ProjectResponse;
import com.Agent.javabackend.entity.MessageContainer.Project;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import com.Agent.javabackend.exception.ProjectWorkspacePreparationException;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;

@Service
public class ProjectServiceImpl implements ProjectService {
    private final ProjectMapper projects;
    private final PythonAgentClient pythonAgentClient;
    private final LocalDirectoryService localDirectoryService;
    private final String activeProfile;

    public ProjectServiceImpl(ProjectMapper projects,
                              PythonAgentClient pythonAgentClient,
                              LocalDirectoryService localDirectoryService,
                              @Value("${spring.profiles.active:local}") String activeProfile) {
        this.projects = projects;
        this.pythonAgentClient = pythonAgentClient;
        this.localDirectoryService = localDirectoryService;
        this.activeProfile = activeProfile;
    }

    @Override
    public ProjectResponse create(CreateProjectRequest request, String ownerId) {
        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        Project project = new Project();
        project.setId(UUID.randomUUID().toString());
        project.setName(request.getName());
        project.setDescription(request.getDescription());
        if (isCloud()) {
            // owner_id 只取服务端认证结果，不读取任何客户端提交的所有者字段。
            project.setOwnerId(requireOwnerId(ownerId));
        } else {
            if (request.getLocalPath() == null || request.getLocalPath().isBlank()) {
                throw new BaseException(ErrorCode.INVALID_ARGUMENT, "本地项目目录不得为空");
            }
            // 保存 local_path 前重新检查存在、目录类型、允许根和权限。
            project.setLocalPath(localDirectoryService.validateBindableDirectory(request.getLocalPath()));
        }
        project.setCreatedAt(now);
        project.setUpdatedAt(now);
        try {
            projects.insert(project);
        } catch (RuntimeException exception) {
            if (!isCloud()) {
                throw new BaseException(ErrorCode.LOCAL_PROJECT_SAVE_FAILED, exception);
            }
            throw exception;
        }

        /*
         * 该方法刻意不在数据库事务中执行：insert 返回时项目已经提交，
         * 随后才允许 Python 查询项目并准备目录，避免事务里等待网络。
         */
        if (isCloud()) {
            prepareWorkspaceAfterCommit(project.getId(), "项目已创建，但目录准备失败");
        }
        return toResponse(project);
    }

    @Override
    public ProjectResponse get(String projectId, String ownerId) {
        Project project = requireOwnedProject(projectId, ownerId);
        // 云端进入已有项目时补建缺失目录；local 直接使用 SQLite 中的真实目录。
        if (isCloud()) {
            prepareWorkspaceAfterCommit(project.getId(), "项目目录准备失败");
        }
        return toResponse(project);
    }

    @Override
    public List<ProjectResponse> list(String ownerId) {
        return projects.findAllByOwnerId(ownerIdForQuery(ownerId)).stream()
                .map(this::toResponse).toList();
    }

    @Override
    public Project requireOwnedProject(String projectId, String ownerId) {
        return projects.findByIdAndOwnerId(projectId, ownerIdForQuery(ownerId))
                .orElseThrow(() -> new BaseException(ErrorCode.PROJECT_NOT_FOUND));
    }

    @Override
    public void prepareWorkspace(String projectId, String ownerId) {
        requireOwnedProject(projectId, ownerId);
        if (isCloud()) {
            prepareWorkspaceAfterCommit(projectId, "项目目录准备失败");
        }
    }

    private void prepareWorkspaceAfterCommit(String projectId, String failureMessage) {
        try {
            pythonAgentClient.prepareWorkspace(projectId);
        } catch (BaseException exception) {
            throw new ProjectWorkspacePreparationException(projectId, failureMessage, exception);
        }
    }

    private String ownerIdForQuery(String ownerId) {
        return isCloud() ? requireOwnerId(ownerId) : null;
    }

    private String requireOwnerId(String ownerId) {
        if (ownerId == null || ownerId.isBlank()) {
            throw new BaseException(ErrorCode.AUTH_TOKEN_INVALID);
        }
        return ownerId;
    }

    private boolean isCloud() {
        return "cloud".equalsIgnoreCase(activeProfile);
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
