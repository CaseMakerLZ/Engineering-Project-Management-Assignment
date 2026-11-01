package com.Agent.javabackend.dto.ProjectFileDTO;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

/** 项目文件树中的一个直接子项。 */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class ProjectFileEntry {
    /** 文件名，不含目录部分。 */
    private String name;
    /** 相对项目根目录的路径，使用 / 分隔。 */
    private String path;
    /** directory 或 file。 */
    private String kind;
    /** 文件字节数；目录为 null。 */
    @JsonProperty("size_bytes")
    private Long sizeBytes;
}
