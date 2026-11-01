package com.Agent.javabackend.dto.LocalDirectoryDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

/** GET /api/local/directories 返回的数据本体。 */
@Data
public class LocalDirectoryBrowseResponse {
    /** 无参数请求时返回根入口；浏览某根时为空数组。 */
    private List<LocalDirectoryRoot> roots;
    @JsonProperty("root_id")
    private String rootId;
    /** 相对根位置的路径；根入口请求为 null。 */
    private String path;
    @JsonProperty("absolute_path")
    private String absolutePath;
    private List<LocalDirectoryEntry> entries;
    @JsonProperty("next_cursor")
    private String nextCursor;
}
