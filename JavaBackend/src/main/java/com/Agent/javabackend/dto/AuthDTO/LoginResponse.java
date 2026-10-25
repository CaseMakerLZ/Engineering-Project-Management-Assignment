package com.Agent.javabackend.dto.AuthDTO;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** 登录成功后返回的一次性明文令牌和用户信息。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class LoginResponse {
    private String token;

    @JsonProperty("expires_in")
    private long expiresIn;

    private UserResponse user;
}
