package com.Agent.javabackend.Controller;

import com.Agent.javabackend.Service.AuthService;
import com.Agent.javabackend.auth.AuthPrincipal;
import com.Agent.javabackend.dto.AuthDTO.AuthCredentialsRequest;
import com.Agent.javabackend.dto.AuthDTO.LoginResponse;
import com.Agent.javabackend.dto.AuthDTO.UserResponse;
import com.Agent.javabackend.dto.Result;
import jakarta.validation.Valid;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

@Profile("cloud")
@RestController
@RequestMapping("/api/auth")
public class UserController {
    private final AuthService authService;

    public UserController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/register")
    public Result<UserResponse> register(@Valid @RequestBody AuthCredentialsRequest request) {
        return Result.success(authService.register(request));
    }

    @PostMapping("/login")
    public Result<LoginResponse> login(@Valid @RequestBody AuthCredentialsRequest request) {
        return Result.success(authService.login(request));
    }

    @GetMapping("/me")
    public Result<UserResponse> me(
            @RequestAttribute(AuthPrincipal.REQUEST_ATTRIBUTE) AuthPrincipal principal) {
        return Result.success(authService.currentUser(principal));
    }

    @PostMapping("/logout")
    public Result<Void> logout(
            @RequestAttribute(AuthPrincipal.REQUEST_ATTRIBUTE) AuthPrincipal principal) {
        authService.logout(principal);
        return Result.success();
    }
}
