# player_template.py
"""
Simplified PokerBot – Player Template

You ONLY need to modify the `decide_action` function below.

The tournament engine (master.py) will:
  - Call this script once per round.
  - Send you a single JSON object on stdin describing the game state.
  - Expect a JSON object on stdout: {"action": "FOLD" or "CALL" or "RAISE"}

Your job:
  - Read the state.
  - Decide whether to FOLD / CALL / RAISE using a *quantitative* strategy.
  - Output the action as JSON.

You are free to:
  - Add helper functions.
  - Use probability / EV calculations.
  - Use opponent statistics for adaptive strategies.
  - As long as you keep the I/O format the same.
"""

import json
import sys
from typing import List, Tuple


# -------------------------
# 1. Basic card utilities
# -------------------------

# Ranks from lowest to highest. T = 10, J = Jack, Q = Queen, K = King, A = Ace.
RANKS = "23456789TJQKA"
# Map rank character -> numeric value (2..14)
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}  # 2..14 (A=14)


def parse_card(card_str: str) -> Tuple[int, str]:
    """
    Convert a string like "AH" or "7D" into (rank_value, suit).

    Example:
        "AH" -> (14, 'H')
        "7D" -> (7, 'D')

    card_str[0]: rank in "23456789TJQKA"
    card_str[1]: suit in "CDHS"  (Clubs, Diamonds, Hearts, Spades)
    """
    return RANK_VALUE[card_str[0]], card_str[1]


def is_straight_3(rank_values: List[int]) -> Tuple[bool, int]:
    """
    Check if 3 cards form a straight under our custom rules.

    Rules:
      - 3 cards are a straight if they are in sequence.
      - A can be:
          * LOW in A-2-3  (treated as the LOWEST straight)
          * HIGH in Q-K-A (treated as the highest normal case)
      - Return:
          (is_straight: bool, high_card_value_for_straight: int)

    Examples:
      [2, 3, 4]    -> (True, 4)
      [12, 13, 14] -> Q-K-A -> (True, 14)
      [14, 2, 3]   -> A-2-3 -> (True, 3)  (lowest straight)
    """
    r = sorted(rank_values)

    # Normal consecutive: x, x+1, x+2
    if r[0] + 1 == r[1] and r[1] + 1 == r[2]:
        return True, r[2]

    # A-2-3 special: {14,2,3} -> treat as straight with high=3
    if set(r) == {14, 2, 3}:
        return True, 3

    return False, 0


# --------------------------------------
# 2. Hand category evaluation (3 cards)
# --------------------------------------

"""
Hand is always: your 2 hole cards + 1 community card = 3 cards.

We classify them into 6 categories (from weakest to strongest):

  0: HIGH CARD
  1: PAIR
  2: FLUSH
  3: STRAIGHT
  4: TRIPS  (Three of a kind)
  5: STRAIGHT FLUSH

And the *global ranking* is:

  STRAIGHT_FLUSH (5) > TRIPS (4) > STRAIGHT (3) > FLUSH (2) > PAIR (1) > HIGH_CARD (0)

This function only returns the category index 0..5,
not the tie-break details (you don't strictly need tie-breaks inside your bot).
"""


def hand_category(hole: List[str], table: str) -> int:
    """
    Compute the hand category for your 3-card hand.

    Input:
        hole  = ["AS", "TD"], etc. (your two private cards)
        table = "7H"           (community card)

    Returns:
        0..5 as defined above.
    """
    cards = hole + [table]
    rank_values, suits = zip(*[parse_card(c) for c in cards])
    flush = len(set(suits)) == 1  # True if all 3 suits are the same

    # Count how many times each rank appears
    counts = {}
    for v in rank_values:
        counts[v] = counts.get(v, 0) + 1

    straight, _ = is_straight_3(list(rank_values))

    if straight and flush:
        return 5  # Straight Flush
    if 3 in counts.values():
        return 4  # Trips
    if straight:
        return 3  # Straight
    if flush:
        return 2  # Flush
    if 2 in counts.values():
        return 1  # Pair
    return 0      # High Card


# ----------------------------------------
# 3. Scoring summary (for your reference)
# ----------------------------------------
"""
IMPORTANT: these are the points awarded PER ROUND
depending on the actions and showdown result.

Notation:
  - "Showdown" means nobody folded: cards are compared.
  - result = which player wins the hand, not part of your code directly.

Fold scenarios (no showdown):
  P1: FOLD, P2: FOLD  ->  (0, 0)
  P1: FOLD, P2: CALL  ->  (-1, +2)
  P1: FOLD, P2: RAISE ->  (-1, +3)
  P1: CALL, P2: FOLD  ->  (+2, -1)
  P1: RAISE, P2: FOLD ->  (+3, -1)

Showdown scenarios (someone has better hand):
  Both CALL:
    - P1 wins: (+2, -2)
    - P2 wins: (-2, +2)

  P1 RAISE, P2 CALL:
    - P1 wins: (+3, -2)
    - P2 wins: (-3, +2)

  P1 CALL, P2 RAISE:
    - P1 wins: (+2, -3)
    - P2 wins: (-2, +3)

  P1 RAISE, P2 RAISE (High-Risk round):
    - P1 wins: (+3, -3)
    - P2 wins: (-3, +3)

Any showdown where hands are *exactly* identical:
  -> (0, 0)

Your bot does NOT see the opponent's current action,
but it CAN see opponent action frequencies over previous rounds
(via `opponent_stats`).
Use this to think in terms of EXPECTED VALUE (EV), not just raw hand strength.
"""
# -------------------------------------------------
# 4. Additional helper functions that we have added
# -------------------------------------------------

def get_hand_tuple(hole, table):
    """Converts a 3-card hand into a tuple for easy comparison."""
    category = hand_category(hole, table)
    # Get numeric values: [14, 10, 2] etc.
    vals = sorted([parse_card(c)[0] for c in (hole + [table])], reverse=True)
    
    if category == 1: # Pair logic: (Category, PairValue, Kicker)
        pair_val = max(v for v in vals if vals.count(v) == 2)
        kicker = max(v for v in vals if vals.count(v) == 1)
        return (1, pair_val, kicker, 0)
    
    if category in [3, 5]: # Straight/Straight Flush: (Category, HighCard)
        # Use your is_straight_3 helper to get the true high card (handles A-2-3)
        _, high_val = is_straight_3(vals)
        return (category, high_val, 0, 0)

    # Categories 0 (High), 2 (Flush), 4 (Trips): (Category, High, Mid, Low)
    return (category, vals[0], vals[1], vals[2])

def probability_of_win(hole_cards, table_card):
    """
    Exhaustively calculates exact P(win) using manual nested loops.
    Evaluates all 1,176 possible opponent hands (49C2).
    """
    win_count = 0
    
    # Create the deck and remove the 3 cards we know (2 hole + 1 table)
    deck = [r + s for r in "23456789TJQKA" for s in "CDHS"]
    for c in (hole_cards + [table_card]): 
        deck.remove(c)
    
    # Pre-calculate our own hand tuple once to save time
    my_tuple = get_hand_tuple(hole_cards, table_card)
    remaining_cards = deck  # This has exactly 49 cards
    total_scenarios = 0 #which will be 49C2 = 1176

    # Manual Nested Loops to visit every unique 2-card combination
    for i in range(len(remaining_cards)):
        for j in range(i + 1, len(remaining_cards)): #j=i+1 to prevent double counting
            total_scenarios += 1
            opp_hole = [remaining_cards[i], remaining_cards[j]]
            opp_tuple = get_hand_tuple(opp_hole, table_card)
            
            if my_tuple > opp_tuple:
                win_count += 1
            elif my_tuple == opp_tuple:
                # A tie results in 0 points, which is the midpoint between win and loss
                win_count += 0.5     
    # Return the deterministic probability (no sampling noise like in case of Monte-Carlo)
    return win_count / total_scenarios 

def get_smoothed_rate(actual: int,round_no: int,prior_rate: float,total_rounds: int) -> float:
    """calculates smoothed fold, call and raise rate"""
    k=max(20,0.10*total_rounds)# k is taken to be maximum of 20 and 10% of the total matches in the duel

    #if round_no==1 then prior rate will be returned directly
    if(round_no-1)==0:
        return prior_rate
    
    #calculating the smoothed rate
    smoothed_rate=(actual+k*prior_rate)/(round_no -1 +k)

    return smoothed_rate

# -----------------------------------
# 5. Main strategy function to edit
# -----------------------------------

def decide_action(state: dict) -> str:
    """modified decide_action function"""
    #extracting the basic inforamtion from the input state dictionary
    hole = state["your_hole"]                 
    table = state["table_card"]               
    opp = state.get("opponent_stats") or {"fold": 0, "call": 0, "raise": 0}
    round_number = state.get("round", 1)
    my_pts=state["your_points"]
    opp_pts=state["opponent_points"]
    total_rounds=state["total_rounds"]

    #calculating the difference between my score and opponents score
    margin=my_pts-opp_pts

    #calculating the probability of win and loss using exhaustive simulation
    p_win=probability_of_win(hole,table)
    p_loss=1-p_win

    #calculating the smoothed fold,call and raise rate
    p_opp_fold=get_smoothed_rate(opp["fold"],round_number,0.3,total_rounds)
    p_opp_raise=get_smoothed_rate(opp["raise"],round_number,0.2,total_rounds)
    p_opp_call=get_smoothed_rate(opp["call"],round_number,0.5,total_rounds)

    #calculating the EV of fold, call and raise using the probability of win and smoothed fold, call and raise rate
    ev_fold=-1*(p_opp_raise+p_opp_call)
    ev_call=2*p_opp_fold+p_opp_raise*(2*p_win-2*p_loss)+p_opp_call*(2*p_win-2*p_loss)
    ev_raise=3*p_opp_fold+p_opp_raise*(3*p_win-3*p_loss)+p_opp_call*(3*p_win-3*p_loss)

    #adjustemt to manage risk
    #when in the ending of the duel
    if(round_number>0.80*total_rounds):
        #if margin is high, then it's good so we will play safe hence decreasing the EV of raise is reduced 
        if(margin>max(10,0.03*total_rounds)):
            ev_raise+=-0.5
        #if opponent score is higher than ours and the difference is also relatively large, we will take risk to increase our score hence increasing the EV of raise
        elif(margin<-max(10,0.03*total_rounds)):
            ev_raise+=0.5

    #finally returning the best option("RAISE","CALL" or "FOLD") depending upon the EV comparision
    list_choices=["RAISE","CALL","FOLD"]
    list_evs=[ev_raise,ev_call,ev_fold]
    
    return_value=list_choices[list_evs.index(max(list_evs))]

    return return_value

# -----------------------------
# 6. I/O glue (do not touch)
# -----------------------------

def main():
    """
    DO NOT modify this unless you know what you're doing.

    It:
      - Reads one JSON object from stdin.
      - Calls decide_action(state).
      - Writes {"action": "..."} as JSON to stdout.
    """
    raw = sys.stdin.read().strip()
    try:
        state = json.loads(raw) if raw else {}
    except Exception:
        state = {}

    action = decide_action(state)

    # Safety check: default to CALL if something invalid is returned
    if action not in {"FOLD", "CALL", "RAISE"}:
        action = "CALL"

    sys.stdout.write(json.dumps({"action": action}))


if __name__ == "__main__":
    main()
