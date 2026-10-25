package com.Agent.javabackend.dto.AuthDTO;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 注册和登录共用的用户名、密码请求体。 */
@Data
public class AuthCredentialsRequest {
    @NotBlank(message = "用户名必须为4-20位字母、数字或下划线")
    @Pattern(
            regexp = "^[A-Za-z0-9_]{4,20}$",
            message = "用户名必须为4-20位字母、数字或下划线")
    private String username;

    @NotBlank(message = "密码长度必须为8-32位")
    @Size(min = 8, max = 32, message = "密码长度必须为8-32位")
    private String password;
}
