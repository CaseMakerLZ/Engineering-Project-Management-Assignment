package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.ProjectService;
import com.Agent.javabackend.auth.AuthPrincipal;
import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.dto.ProjectDTO.ProjectResponse;
import com.Agent.javabackend.dto.Result;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {
    private final ProjectService projectService;

    public ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @GetMapping
    public Result<List<ProjectResponse>> list(
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(projectService.list(ownerId(principal)));
    }

    @PostMapping
    public Result<ProjectResponse> create(
            @Valid @RequestBody CreateProjectRequest request,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(projectService.create(request, ownerId(principal)));
    }

    @GetMapping("/{projectId}")
    public Result<ProjectResponse> get(
            @PathVariable String projectId,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        return Result.success(projectService.get(projectId, ownerId(principal)));
    }

    /** local 模式没有认证拦截器，principal 为空；cloud 模式由 AuthInterceptor 写入。 */
    private String ownerId(AuthPrincipal principal) {
        return principal == null || principal.user() == null ? null : principal.user().getUserId();
    }
}
