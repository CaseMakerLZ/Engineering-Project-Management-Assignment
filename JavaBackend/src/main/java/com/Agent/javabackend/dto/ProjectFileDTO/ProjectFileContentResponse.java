package com.Agent.javabackend.dto.ProjectFileDTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

/** Python 内部文本预览接口返回的数据本体。 */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ProjectFileContentResponse {
    @JsonProperty("project_id")
    private String projectId;
    /** 相对项目根目录的文件路径。 */
    private String path;
    /** UTF-8 文本内容；首版只读，不做静默截断。 */
    private String content;
    @JsonProperty("size_bytes")
    private Long sizeBytes;
    /** 当前固定为 utf-8。 */
    private String encoding;
}
