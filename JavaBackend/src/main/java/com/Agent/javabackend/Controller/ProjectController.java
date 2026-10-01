package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.ProjectService;
import com.Agent.javabackend.dto.ProjectDTO.CreateProjectRequest;
import com.Agent.javabackend.dto.ProjectDTO.ProjectResponse;
import com.Agent.javabackend.dto.Result;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {
    private final ProjectService projectService;

    public ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @PostMapping
    public Result<ProjectResponse> create(@Valid @RequestBody CreateProjectRequest request) {
        return Result.success(projectService.create(request));
    }

    @GetMapping("/{projectId}")
    public Result<ProjectResponse> get(@PathVariable String projectId) {
        return Result.success(projectService.get(projectId));
    }
}
