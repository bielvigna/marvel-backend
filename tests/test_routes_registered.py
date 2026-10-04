def test_profile_friend_and_challenge_routes_are_registered(app):
    registered = {
        (path, method.upper()) for path, operations in app.openapi()["paths"].items() for method in operations
    }
    expected = {
        ("/v1/profile/me", "GET"),
        ("/v1/profile/me", "PATCH"),
        ("/v1/friends", "GET"),
        ("/v1/friends/search", "GET"),
        ("/v1/friend-requests", "GET"),
        ("/v1/friend-requests", "POST"),
        ("/v1/friend-requests/{request_id}/accept", "POST"),
        ("/v1/friend-requests/{request_id}/decline", "POST"),
        ("/v1/challenges", "GET"),
        ("/v1/challenges", "POST"),
        ("/v1/challenges/{challenge_id}/accept", "POST"),
        ("/v1/challenges/{challenge_id}/decline", "POST"),
        ("/v1/matchmaking/queue", "POST"),
        ("/v1/matchmaking/queue", "GET"),
        ("/v1/matchmaking/queue", "DELETE"),
        ("/v1/matches/{match_id}", "GET"),
        ("/v1/matches/{match_id}/teams", "PUT"),
        ("/v1/matches/{match_id}/actions", "POST"),
    }

    assert expected <= registered
