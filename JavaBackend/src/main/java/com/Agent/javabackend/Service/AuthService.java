package com.Agent.javabackend.Service;

import com.Agent.javabackend.auth.AuthPrincipal;
import com.Agent.javabackend.dto.AuthDTO.AuthCredentialsRequest;
import com.Agent.javabackend.dto.AuthDTO.LoginResponse;
import com.Agent.javabackend.dto.AuthDTO.UserResponse;

/** 成员三负责的云端用户认证服务。 */
public interface AuthService {
    UserResponse register(AuthCredentialsRequest request);

    LoginResponse login(AuthCredentialsRequest request);

    AuthPrincipal authenticate(String rawToken);

    UserResponse currentUser(AuthPrincipal principal);

    void logout(AuthPrincipal principal);
}
