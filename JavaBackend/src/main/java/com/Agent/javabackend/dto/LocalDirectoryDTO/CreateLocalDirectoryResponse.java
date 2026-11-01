package com.Agent.javabackend.dto.LocalDirectoryDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** POST /api/local/directories 创建成功后的数据本体。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class CreateLocalDirectoryResponse {
    @JsonProperty("root_id")
    private String rootId;
    private String path;
    @JsonProperty("absolute_path")
    private String absolutePath;
}
