package com.Agent.javabackend.Service;

import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.dto.ProjectDTO.ProjectResponse;
import com.Agent.javabackend.entity.MessageContainer.Project;

import java.util.List;

public interface ProjectService {
    ProjectResponse create(CreateProjectRequest request, String ownerId);
    ProjectResponse get(String projectId, String ownerId);
    List<ProjectResponse> list(String ownerId);

    /** 读取当前用户可访问的项目；不存在或不属于当前用户时统一按项目不存在处理。 */
    Project requireOwnedProject(String projectId, String ownerId);

    /** 再次调用幂等的工作区准备接口，供已有项目或提交任务前补建目录。 */
    void prepareWorkspace(String projectId, String ownerId);
}
