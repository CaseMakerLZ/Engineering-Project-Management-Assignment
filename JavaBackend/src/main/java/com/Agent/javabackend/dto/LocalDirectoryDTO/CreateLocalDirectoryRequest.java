package com.Agent.javabackend.dto.LocalDirectoryDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** POST /api/local/directories 的请求体。 */
@Data
public class CreateLocalDirectoryRequest {
    @NotBlank(message = "root_id 不得为空")
    @JsonProperty("root_id")
    private String rootId;

    /** 父目录相对路径；根位置下创建时为空串或省略。 */
    @JsonProperty("parent_path")
    private String parentPath;

    @NotBlank(message = "目录名不得为空")
    @Size(max = 255, message = "目录名长度不得超过 255")
    private String name;
}
