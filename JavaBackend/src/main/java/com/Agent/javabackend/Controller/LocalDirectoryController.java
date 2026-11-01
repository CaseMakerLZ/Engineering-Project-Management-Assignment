package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.LocalDirectoryService;
import com.Agent.javabackend.dto.LocalDirectoryDTO.CreateLocalDirectoryRequest;
import com.Agent.javabackend.dto.LocalDirectoryDTO.CreateLocalDirectoryResponse;
import com.Agent.javabackend.dto.LocalDirectoryDTO.LocalDirectoryBrowseResponse;
import com.Agent.javabackend.dto.Result;
import jakarta.validation.Valid;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * local 模式专用的本机目录点选接口。
 *
 * cloud profile 不注册这个 Controller，因此这两个路径在云端为 404。
 */
@Profile("local")
@RestController
@RequestMapping("/api/local")
public class LocalDirectoryController {
    private final LocalDirectoryService localDirectoryService;

    public LocalDirectoryController(LocalDirectoryService localDirectoryService) {
        this.localDirectoryService = localDirectoryService;
    }

    @GetMapping("/directories")
    public ResponseEntity<Result<LocalDirectoryBrowseResponse>> browse(
            @RequestParam(name = "root_id", required = false) String rootId,
            @RequestParam(name = "path", required = false) String path,
            @RequestParam(name = "page_size", defaultValue = "100") int pageSize,
            @RequestParam(name = "cursor", required = false) String cursor) {
        LocalDirectoryBrowseResponse data =
                localDirectoryService.browse(rootId, path, pageSize, cursor);
        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .header("X-Content-Type-Options", "nosniff")
                .body(Result.success(data));
    }

    @PostMapping("/directories")
    @ResponseStatus(HttpStatus.CREATED)
    public ResponseEntity<Result<CreateLocalDirectoryResponse>> create(
            @Valid @RequestBody CreateLocalDirectoryRequest request) {
        CreateLocalDirectoryResponse data = localDirectoryService.create(
                request.getRootId(), request.getParentPath(), request.getName());
        return ResponseEntity.status(HttpStatus.CREATED)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .header("X-Content-Type-Options", "nosniff")
                .body(Result.success(data));
    }
}
