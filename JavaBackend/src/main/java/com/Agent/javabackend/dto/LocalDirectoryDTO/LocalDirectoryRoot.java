package com.Agent.javabackend.dto.LocalDirectoryDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** 服务端允许浏览的根位置别名；不是项目 ID。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class LocalDirectoryRoot {
    @JsonProperty("root_id")
    private String rootId;
    private String name;
}
