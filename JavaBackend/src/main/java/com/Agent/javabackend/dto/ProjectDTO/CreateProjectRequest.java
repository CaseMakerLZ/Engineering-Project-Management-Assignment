package com.Agent.javabackend.dto.ProjectDTO;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 创建项目时，前端提交的数据。 */
@Data
public class CreateProjectRequest {
    /** 项目名称。 */
    @NotBlank(message = "项目名称不得为空")
    @Size(max = 128, message = "项目名称长度不得超过128")
    private String name;

    /** 项目描述，可以为空。 */
    @Size(max = 2000, message = "项目描述长度不得超过2000")
    private String description;
}
