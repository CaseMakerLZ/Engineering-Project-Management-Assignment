package com.Agent.javabackend.dto.ProjectFileDTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

/** Python 内部项目文件树接口返回的数据本体。 */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ProjectFileTreeResponse {
    @JsonProperty("project_id")
    private String projectId;
    /** 当前目录相对路径，根目录为空串。 */
    private String path;
    /** 当前页的直接子项，目录优先并稳定排序。 */
    private List<ProjectFileEntry> entries;
    /** 非空时表示还有下一页。 */
    @JsonProperty("next_cursor")
    private String nextCursor;
}
