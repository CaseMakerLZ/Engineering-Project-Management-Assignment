package com.Agent.javabackend.Service.impl;

import com.Agent.javabackend.Mapper.AuthSessionMapper;
import com.Agent.javabackend.Mapper.UserMapper;
import com.Agent.javabackend.Service.AuthService;
import com.Agent.javabackend.auth.AuthPrincipal;
import com.Agent.javabackend.dto.AuthDTO.AuthCredentialsRequest;
import com.Agent.javabackend.dto.AuthDTO.LoginResponse;
import com.Agent.javabackend.dto.AuthDTO.UserResponse;
import com.Agent.javabackend.entity.MessageContainer.AuthSession;
import com.Agent.javabackend.entity.MessageContainer.User;
import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;

/** 注册、登录、令牌校验和注销的业务实现。 */
@Profile("cloud")
@Service
public class AuthServiceImpl implements AuthService {
    static final long TOKEN_LIFETIME_SECONDS = Duration.ofDays(7).toSeconds();
    private static final int TOKEN_BYTES = 32;

    private final UserMapper users;
    private final AuthSessionMapper sessions;
    private final PasswordEncoder passwordEncoder;
    private final SecureRandom secureRandom;
    private final String dummyPasswordHash;

    public AuthServiceImpl(
            UserMapper users,
            AuthSessionMapper sessions,
            PasswordEncoder passwordEncoder) {
        this.users = users;
        this.sessions = sessions;
        this.passwordEncoder = passwordEncoder;
        this.secureRandom = new SecureRandom();
        this.dummyPasswordHash = passwordEncoder.encode("dummy-password-value");
    }

    @Override
    @Transactional
    public UserResponse register(AuthCredentialsRequest request) {
        String username = request.getUsername().trim();
        if (users.findByUsername(username).isPresent()) {
            throw new BaseException(ErrorCode.USERNAME_ALREADY_EXISTS);
        }

        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        User user = new User();
        user.setUserId(UUID.randomUUID().toString());
        user.setUsername(username);
        user.setPasswordHash(passwordEncoder.encode(request.getPassword()));
        user.setStatus("ACTIVE");
        user.setCreatedAt(now);
        user.setUpdatedAt(now);

        try {
            users.insert(user);
        } catch (DuplicateKeyException exception) {
            throw new BaseException(ErrorCode.USERNAME_ALREADY_EXISTS, exception);
        }
        return toResponse(user);
    }

    @Override
    @Transactional
    public LoginResponse login(AuthCredentialsRequest request) {
        User user = users.findByUsername(request.getUsername().trim()).orElse(null);
        if (user == null) {
            // 对不存在的用户名也执行一次 bcrypt 校验，避免响应耗时明显泄露账号是否存在。
            passwordEncoder.matches(request.getPassword(), dummyPasswordHash);
            throw new BaseException(ErrorCode.BAD_CREDENTIALS);
        }

        boolean passwordMatches = passwordEncoder.matches(request.getPassword(), user.getPasswordHash());
        if (!"ACTIVE".equals(user.getStatus()) || !passwordMatches) {
            throw new BaseException(ErrorCode.BAD_CREDENTIALS);
        }

        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        String rawToken = generateToken();
        AuthSession session = new AuthSession();
        session.setSessionId(UUID.randomUUID().toString());
        session.setUserId(user.getUserId());
        session.setTokenHash(sha256Hex(rawToken));
        session.setCreatedAt(now);
        session.setExpiresAt(now.plusSeconds(TOKEN_LIFETIME_SECONDS));
        sessions.insert(session);
        users.updateLastLogin(user.getUserId(), now);

        return new LoginResponse(rawToken, TOKEN_LIFETIME_SECONDS, toResponse(user));
    }

    @Override
    public AuthPrincipal authenticate(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) {
            throw new BaseException(ErrorCode.AUTH_TOKEN_INVALID);
        }

        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        AuthSession session = sessions.findActiveByTokenHash(sha256Hex(rawToken), now)
                .filter(candidate -> candidate.getRevokedAt() == null)
                .filter(candidate -> candidate.getExpiresAt().isAfter(now))
                .orElseThrow(() -> new BaseException(ErrorCode.AUTH_TOKEN_INVALID));

        User user = users.findById(session.getUserId())
                .filter(candidate -> "ACTIVE".equals(candidate.getStatus()))
                .orElseThrow(() -> new BaseException(ErrorCode.AUTH_TOKEN_INVALID));
        return new AuthPrincipal(user, session.getSessionId());
    }

    @Override
    public UserResponse currentUser(AuthPrincipal principal) {
        return toResponse(principal.user());
    }

    @Override
    @Transactional
    public void logout(AuthPrincipal principal) {
        sessions.revokeById(principal.sessionId(), OffsetDateTime.now(ZoneOffset.UTC));
    }

    private String generateToken() {
        byte[] token = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(token);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(token);
    }

    private String sha256Hex(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 Java 运行环境不支持 SHA-256", exception);
        }
    }

    private UserResponse toResponse(User user) {
        return new UserResponse(user.getUserId(), user.getUsername());
    }
}
