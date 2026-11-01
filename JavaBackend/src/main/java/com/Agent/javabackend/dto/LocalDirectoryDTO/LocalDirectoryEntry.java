package com.Agent.javabackend.dto.LocalDirectoryDTO;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** 本地目录浏览结果中的一个直接子目录。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class LocalDirectoryEntry {
    private String name;
    /** 相对根位置的路径，使用 / 分隔。 */
    private String path;
}
