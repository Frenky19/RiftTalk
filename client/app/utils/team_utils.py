from typing import Any, Dict, List, Optional, Tuple


def _team_id_from_value(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value in (100, 200) else None
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('blue', 'order', 'teamone', 'team_one'):
            return 100
        if v in ('red', 'chaos', 'teamtwo', 'team_two'):
            return 200
        try:
            iv = int(v)
        except ValueError:
            return None
        return iv if iv in (100, 200) else None
    return None


def _normalize_team_container(
    team: Any,
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    if isinstance(team, dict):
        players = team.get('players', [])
        team_id = _team_id_from_value(
            team.get('teamId') or team.get('teamID') or team.get('team')
        )
        return (players if isinstance(players, list) else []), team_id
    if isinstance(team, list):
        return team, None
    return [], None


def _split_players_by_team_id(
    players: List[Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    blue: List[Dict[str, Any]] = []
    red: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []
    for player in players:
        if not isinstance(player, dict):
            continue
        team_id = _team_id_from_value(
            player.get('teamId')
            or player.get('teamID')
            or player.get('team')
            or player.get('teamSide')
        )
        if team_id == 100:
            blue.append(player)
        elif team_id == 200:
            red.append(player)
        else:
            unknown.append(player)
    return blue, red, unknown


def extract_teams_from_session(
    session: Dict[str, Any],
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    if not isinstance(session, dict):
        return None

    def by_team_id(players: List[Any]) -> Optional[Tuple[List[Any], List[Any]]]:
        blue, red, _ = _split_players_by_team_id(players)
        if blue or red:
            return blue, red
        return None

    game_data = session.get('gameData')
    if isinstance(game_data, dict):
        team_one_players, team_one_id = _normalize_team_container(
            game_data.get('teamOne')
        )
        team_two_players, team_two_id = _normalize_team_container(
            game_data.get('teamTwo')
        )
        if team_one_id or team_two_id:
            blue_team = (
                team_one_players if team_one_id == 100 else
                team_two_players if team_two_id == 100 else []
            )
            red_team = (
                team_one_players if team_one_id == 200 else
                team_two_players if team_two_id == 200 else []
            )
            if blue_team or red_team:
                return {'blue_team': blue_team, 'red_team': red_team}
        by_id = by_team_id(team_one_players + team_two_players)
        if by_id:
            blue_team, red_team = by_id
            return {'blue_team': blue_team, 'red_team': red_team}
        if team_one_players or team_two_players:
            return {'blue_team': team_one_players, 'red_team': team_two_players}

    teams = session.get('teams')
    if isinstance(teams, list) and teams:
        normalized = [_normalize_team_container(team) for team in teams]
        team_id_map = {
            team_id: players for players, team_id in normalized if team_id
        }
        if team_id_map:
            return {
                'blue_team': team_id_map.get(100, []),
                'red_team': team_id_map.get(200, []),
            }
        all_players = []
        for players, _ in normalized:
            all_players.extend(players)
        by_id = by_team_id(all_players)
        if by_id:
            blue_team, red_team = by_id
            return {'blue_team': blue_team, 'red_team': red_team}
        if len(normalized) >= 2:
            return {
                'blue_team': normalized[0][0],
                'red_team': normalized[1][0],
            }

    my_team = session.get('myTeam', [])
    their_team = session.get('theirTeam', [])
    if my_team or their_team:
        by_id = by_team_id(list(my_team) + list(their_team))
        if by_id:
            blue_team, red_team = by_id
            return {'blue_team': blue_team, 'red_team': red_team}
        return {'blue_team': list(my_team), 'red_team': list(their_team)}

    return None
