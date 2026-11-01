package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.ProjectFileService;
import com.Agent.javabackend.auth.AuthPrincipal;
import com.Agent.javabackend.dto.ProjectFileDTO.ProjectFileContentResponse;
import com.Agent.javabackend.dto.ProjectFileDTO.ProjectFileTreeResponse;
import com.Agent.javabackend.dto.Result;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 云端项目文件树、文本预览、单文件下载和项目 ZIP 下载。 */
@RestController
@RequestMapping("/api/projects/{projectId}")
public class ProjectFileController {
    private final ProjectFileService projectFileService;

    public ProjectFileController(ProjectFileService projectFileService) {
        this.projectFileService = projectFileService;
    }

    @GetMapping("/files/tree")
    public ResponseEntity<Result<ProjectFileTreeResponse>> tree(
            @PathVariable String projectId,
            @RequestParam(name = "path", defaultValue = "") String path,
            @RequestParam(name = "page_size", defaultValue = "100") int pageSize,
            @RequestParam(name = "cursor", required = false) String cursor,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        ProjectFileTreeResponse data = projectFileService.tree(
                projectId, path, pageSize, cursor, ownerId(principal));
        return noStore(Result.<ProjectFileTreeResponse>success(data));
    }

    @GetMapping("/files/content")
    public ResponseEntity<Result<ProjectFileContentResponse>> content(
            @PathVariable String projectId,
            @RequestParam(name = "path") String path,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal) {
        ProjectFileContentResponse data = projectFileService.content(
                projectId, path, ownerId(principal));
        return noStore(Result.<ProjectFileContentResponse>success(data));
    }

    @GetMapping("/files/download")
    public void download(
            @PathVariable String projectId,
            @RequestParam(name = "path") String path,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal,
            HttpServletResponse response) {
        projectFileService.download(projectId, path, ownerId(principal), response);
    }

    @GetMapping("/archive")
    public void archive(
            @PathVariable String projectId,
            @RequestAttribute(value = AuthPrincipal.REQUEST_ATTRIBUTE, required = false)
            AuthPrincipal principal,
            HttpServletResponse response) {
        projectFileService.archive(projectId, ownerId(principal), response);
    }

    private <T> ResponseEntity<Result<T>> noStore(Result<T> body) {
        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .header("X-Content-Type-Options", "nosniff")
                .body(body);
    }

    private String ownerId(AuthPrincipal principal) {
        return principal == null || principal.user() == null ? null : principal.user().getUserId();
    }
}
