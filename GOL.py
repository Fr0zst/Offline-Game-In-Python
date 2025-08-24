#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A Game Of Lore — interactive, AI-like story engine (single-file, stdlib only).

How to play:
- Run: python GOL.py
- Type the number of a choice to continue.
- Type commands anytime: help, save <slot>, load <slot>, slots, stats, quit
- 8 save slots are available (1–8). Saves are JSON files in ./saves/

Design notes:
- "AI" here is a procedural narrative engine using weighted templates, your state,
  and a seeded RNG to generate scene text and adaptive choices that *matter*.
- Your decisions shift state variables (trust, morality, power, notoriety, etc.)
  which unlock/lock scenes and endings. Multiple playthroughs will diverge.
- No external libraries or internet are needed.
"""
from __future__ import annotations
from textwrap import dedent  # ensure dedent is available at runtime
import os
import sys
import json
import time
import random
import shutil
import hashlib
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Tuple, Optional

SAVE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "saves")
NUM_SLOTS = 8

def ascii_title() -> str:
    # Simple clean ASCII header. Fixed-width and safe for terminals.
    return r"""
 ██╗░░░██╗░█████╗░██╗░░░██╗██╗██████╗░███████╗  ░██████╗  ██╗  ░█████╗░  ██╗░░██╗
╚██╗░██╔╝██╔══██╗██║░░░██║╚█║██╔══██╗██╔════╝  ██╔════╝  ██║  ██╔══██╗  ██║░██╔╝
░╚████╔╝░██║░░██║██║░░░██║░╚╝██████╔╝█████╗░░  ╚█████╗░  ██║  ██║░░╚═╝  █████═╝░
░░╚██╔╝░░██║░░██║██║░░░██║░░░██╔══██╗██╔══╝░░  ░╚═══██╗  ██║  ██║░░██╗  ██╔═██╗░
░░░██║░░░╚█████╔╝╚██████╔╝░░░██║░░██║███████╗  ██████╔╝  ██║  ╚█████╔╝  ██║░╚██╗
░░░╚═╝░░░░╚════╝░░╚═════╝░░░░╚═╝░░╚═╝╚══════╝  ╚═════╝░  ╚═╝  ░╚════╝░  ╚═╝░░╚═╝
                                   A   G A M E   O F   L O R E
    """

# ---------- Data Structures ----------

@dataclass
class StoryState:
    name: str = "Nameless"
    chapter: int = 0
    location: str = "Demon Forest"
    health: int = 80
    power: int = 20
    morality: int = 0            # -100 (ruthless) to +100 (noble)
    notoriety: int = 0           # 0 (unknown) to 100 (infamous)
    trust_demon_lord: int = 10   # 0–100
    bond_demon_lord: int = 0     # long-term relationship metric
    inventory: List[str] = field(default_factory=lambda: ["Torn Cloak", "Rusty Sword"])
    flags: Dict[str, bool] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)
    seed: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict) -> "StoryState":
        # Maintain forward-compat by providing defaults
        defaults = StoryState()
        for k, v in defaults.to_dict().items():
            d.setdefault(k, v)
        # Ensure types
        d["inventory"] = list(d.get("inventory", []))
        d["flags"] = dict(d.get("flags", {}))
        d["history"] = list(d.get("history", []))
        return StoryState(**d)

# ---------- Save / Load ----------

class SaveManager:
    def __init__(self, save_dir: str = SAVE_DIR, num_slots: int = NUM_SLOTS):
        self.save_dir = save_dir
        self.num_slots = num_slots
        os.makedirs(self.save_dir, exist_ok=True)

    def slot_path(self, slot: int) -> str:
        return os.path.join(self.save_dir, f"slot_{slot}.json")

    def save(self, slot: int, state: StoryState) -> str:
        if slot < 1 or slot > self.num_slots:
            raise ValueError(f"Slot must be between 1 and {self.num_slots}.")
        path = self.slot_path(slot)
        data = {
            "version": 1,
            "timestamp": int(time.time()),
            "state": state.to_dict(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def load(self, slot: int) -> StoryState:
        path = self.slot_path(slot)
        if not os.path.exists(path):
            raise FileNotFoundError(f"No save found in slot {slot}.")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = StoryState.from_dict(data.get("state", {}))
        return state

    def list_saves(self) -> List[Tuple[int, str]]:
        result = []
        for s in range(1, self.num_slots + 1):
            path = self.slot_path(s)
            if os.path.exists(path):
                ts = "<unknown>"
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data.get("timestamp", 0)))
                except Exception:
                    pass
                result.append((s, ts))
        return result

# ---------- Narrative Engine ----------

class StoryEngine:
    def __init__(self, rng: random.Random):
        self.rng = rng

    # Utility clamps
    @staticmethod
    def clamp(v: int, lo: int, hi: int) -> int:
        return max(lo, min(hi, v))

    def _p(self, p_true: float) -> bool:
        return self.rng.random() < p_true

    def intro_scene(self, st: StoryState) -> Tuple[str, List[Tuple[str, str]]]:
        st.chapter = 1
        st.location = "Demon Forest — Thornsfall Edge"
        st.flags.setdefault("betrayed", True)
        st.flags.setdefault("met_demon_lord", True)
        st.flags.setdefault("allied", False)
        st.flags.setdefault("vow_revenge", False)
        st.flags.setdefault("seeking_truth", True)
        st.history.append("Banished to the Demon Forest after betrayal by the kingdom and fellow heroes.")
        # Demon Lord intro (female) — name generation
        demon_names = ["Nyx", "Velaria", "Lilithe", "Morrigan", "Eresh", "Seraphine", "Astariel", "Noctra"]
        dl_name = st.flags.get("demon_lord_name") or self.rng.choice(demon_names)
        st.flags["demon_lord_name"] = dl_name

        text = (
            f"You awaken in briars and ash. The kingdom you died to protect has cast you out.\n"
            f"Branches claw your cloak as you stumble through the Demon Forest. A presence watches.\n\n"
            f"She steps from the gloom: the Demon Lord, a girl with eyes like eclipsed moons.\n"
            f'\"I am {dl_name}. Your light reeks of betrayal,\" she says. \"Why should I spare you?\"'
        )

        choices = [
            ("Plead your case: you were framed and seek only the truth.", "intro_plead"),
            ("Swear vengeance: you'll raze the kingdom that betrayed you.", "intro_vengeance"),
            ("Offer a pact: strength for strength—become uneasy allies.", "intro_pact"),
            ("Draw steel: if she wants blood, she'll earn it.", "intro_fight"),
        ]
        return text, choices

    def generate_scene(self, st: StoryState) -> Tuple[str, List[Tuple[str, str]]]:
        """Return (paragraph, choices[(text, tag)...]) based on state."""
        # First special scenes based on flags & arcs:
        if st.chapter == 0:
            return self.intro_scene(st)

        # Possible scene archetypes depending on state
        archetypes = []

        # Relationship scenes
        if st.flags.get("met_demon_lord", False):
            if st.trust_demon_lord >= 60 and not st.flags.get("oath_bound", False):
                archetypes += ["oath_bond"]
            if st.trust_demon_lord >= 30:
                archetypes += ["council", "training"]
            else:
                archetypes += ["tense_camp"]
        # External plot
        if st.flags.get("vow_revenge", False):
            archetypes += ["spy_report", "ambush_king_scouts"]
        if st.morality >= 40:
            archetypes += ["rescue_travelers"]
        if st.morality <= -40:
            archetypes += ["grim_bargain"]
        # General exploration
        archetypes += ["mystic_ruins", "wild_hunt", "whispering_trees"]

        chosen = self.rng.choice(archetypes)

        # Dispatch
        if chosen == "oath_bond":
            return self.scene_oath_bond(st)
        if chosen == "council":
            return self.scene_council(st)
        if chosen == "training":
            return self.scene_training(st)
        if chosen == "tense_camp":
            return self.scene_tense_camp(st)
        if chosen == "spy_report":
            return self.scene_spy_report(st)
        if chosen == "ambush_king_scouts":
            return self.scene_ambush(st)
        if chosen == "rescue_travelers":
            return self.scene_rescue(st)
        if chosen == "grim_bargain":
            return self.scene_grim_bargain(st)
        if chosen == "mystic_ruins":
            return self.scene_ruins(st)
        if chosen == "wild_hunt":
            return self.scene_wild_hunt(st)
        if chosen == "whispering_trees":
            return self.scene_whispers(st)

        # Fallback generic
        return self.scene_tense_camp(st)

    # ----- Scene Implementations -----

    def scene_tense_camp(self, st: StoryState):
        dl = st.flags.get("demon_lord_name", "the Demon Lord")
        st.location = "Forest Camp — Ember Clearing"
        text = (
            f"A small fire sputters beneath twisted pines. {dl} watches you from across the flames.\n"
            f"Trust flickers like kindling. The forest listens."
        )
        choices = [
            ("Share a painful memory to earn her empathy.", "camp_confide"),
            ("Hone your blade in silence; let actions speak.", "camp_silence"),
            ("Probe her motives—why rule the demons at all?", "camp_probe"),
            ("Scout the perimeter; danger stalks the dark.", "camp_scout"),
        ]
        return text, choices

    def scene_training(self, st: StoryState):
        dl = st.flags.get("demon_lord_name", "the Demon Lord")
        st.location = "Obsidian Glade — Training Stones"
        text = (
            f"In the Obsidian Glade, {dl} tests you. Demonic sigils fracture the air.\n"
            f"Power strains your scars as you push beyond mortal limits."
        )
        choices = [
            ("Master a defensive ward to shield the weak.", "train_defense"),
            ("Channel wrath—strike harder, faster, crueler.", "train_wrath"),
            ("Synchronize with {dl}'s rhythm; trust the dance of blades.".format(dl=dl), "train_sync"),
        ]
        return text, choices

    def scene_council(self, st: StoryState):
        dl = st.flags.get("demon_lord_name", "the Demon Lord")
        st.location = "Eclipse Hall — Council of Cinders"
        text = (
            f"{dl}'s lieutenants argue under lanterns filled with captured starlight.\n"
            f"War or peace? Retaliation or secrecy? They seek your counsel."
        )
        choices = [
            ("Advise diplomacy—seek proof of the kingdom's treachery.", "council_diplomacy"),
            ("Plan raids on corrupt nobles and supply lines.", "council_raids"),
            ("Propose a secret parley with a sympathetic hero.", "council_parley"),
        ]
        return text, choices

    def scene_oath_bond(self, st: StoryState):
        dl = st.flags.get("demon_lord_name", "the Demon Lord")
        st.location = "Moonwell — Mirror of Vows"
        text = (
            f"Beside the Moonwell, {dl} offers her hand. \"We choose each other—against crown and fate.\"\n"
            f"The water reflects futures you barely recognize."
        )
        choices = [
            ("Swear an oath of alliance.", "oath_sworn"),
            ("Hesitate—the cost of vows is always hidden.", "oath_hesitate"),
            ("Refuse—freedom above all.", "oath_refuse"),
        ]
        return text, choices

    def scene_spy_report(self, st: StoryState):
        st.location = "Shadespine — Scout's Path"
        text = (
            "A demon scout kneels, breathless: the kingdom moves hunters into the forest.\n"
            "They bear your crest—bait for a public execution."
        )
        choices = [
            ("Intercept and expose the ruse.", "spy_intercept"),
            ("Turn the ambush onto the hunters.", "spy_reverse"),
            ("Ignore; focus on power first.", "spy_ignore"),
        ]
        return text, choices

    def scene_ambush(self, st: StoryState):
        st.location = "Ravine Verge — Broken Bridge"
        text = (
            "You spot royal scouts across a broken bridge, whispering your name like a curse.\n"
            "Their signal mirrors glint. A choice, sharp as shale."
        )
        choices = [
            ("Strike from shadow—no witnesses.", "ambush_shadow"),
            ("Seize a scout alive for information.", "ambush_capture"),
            ("Let them flee; plant fear and rumor.", "ambush_letgo"),
        ]
        return text, choices

    def scene_rescue(self, st: StoryState):
        st.location = "Cairn Road — Bleak Mile"
        text = (
            "A caravan of refugees stumbles under the weight of injustice. Bandits circle.\n"
            "You hear a child's cough beneath the wind."
        )
        choices = [
            ("Shield the caravan; take the blows for them.", "rescue_shield"),
            ("Outwit the bandits with a ruse.", "rescue_ruse"),
            ("Walk away. Mercy is a luxury.", "rescue_walk"),
        ]
        return text, choices

    def scene_grim_bargain(self, st: StoryState):
        dl = st.flags.get("demon_lord_name", "the Demon Lord")
        st.location = "Thorn Altar — Price of Power"
        text = (
            f"A thorned altar hums with forbidden strength. {dl}'s gaze is unreadable.\n"
            "The altar grants might… and takes what you value most."
        )
        choices = [
            ("Bleed for power: sacrifice a memory.", "bargain_memory"),
            ("Spare yourself—reject the altar.", "bargain_reject"),
            ("Offer the altar a token from your betrayers.", "bargain_token"),
        ]
        return text, choices

    def scene_ruins(self, st: StoryState):
        st.location = "Ancient Ruins — Vault of Mists"
        text = (
            "Fog curls around cracked archways. Glyphs speak of heroes who burned their own ages ago.\n"
            "A vault door breathes cold secrets."
        )
        choices = [
            ("Study the glyphs for hidden history.", "ruins_study"),
            ("Force the vault—whatever lies within is yours.", "ruins_force"),
            ("Leave a mark: a promise to return stronger.", "ruins_mark"),
        ]
        return text, choices

    def scene_wild_hunt(self, st: StoryState):
        st.location = "Night Plains — The Wild Hunt"
        text = (
            "Horns sound. Spectral riders rise like storm-surf, seeking a worthy quarry.\n"
            "They circle, inviting chase or challenge."
        )
        choices = [
            ("Race with them; learn their paths.", "hunt_race"),
            ("Challenge the huntmaster to single combat.", "hunt_duel"),
            ("Hide and observe; knowledge first.", "hunt_hide"),
        ]
        return text, choices

    def scene_whispers(self, st: StoryState):
        st.location = "Whispering Trees — Root of Echoes"
        text = (
            "Leaves speak in voices you once trusted. They tell different truths now.\n"
            "One whisper carries the name of a hero who betrayed you."
        )
        choices = [
            ("Follow the whisper to its source.", "whisper_follow"),
            ("Silence the voices with a ward.", "whisper_ward"),
            ("Ask {dl} to listen with you.".format(dl=st.flags.get('demon_lord_name', 'the Demon Lord')), "whisper_together"),
        ]
        return text, choices

    # ----- Apply Choice Effects & Generate Continuation Text -----

    def apply_choice(self, st: StoryState, tag: str) -> str:
        # Modifiers helper
        def mod(attr, delta, lo, hi):
            setattr(st, attr, self.clamp(getattr(st, attr) + delta, lo, hi))

        dl = st.flags.get("demon_lord_name", "the Demon Lord")
        st.chapter += 1

        # Map tags to effects & narration snippets
        # Intro
        if tag == "intro_plead":
            mod("morality", +10, -100, 100)
            mod("trust_demon_lord", +15, 0, 100)
            st.flags["seeking_truth"] = True
            return f"You speak plainly of betrayal. {dl} studies the cracks in your voice and lowers her hand. \"Truth cuts deeper than any blade,\" she says."
        if tag == "intro_vengeance":
            mod("morality", -10, -100, 100)
            mod("power", +10, 0, 100)
            st.flags["vow_revenge"] = True
            mod("trust_demon_lord", +5, 0, 100)
            return f"Vengeance burns like pitch. {dl} smiles—a small, dangerous thing. \"Then we understand each other.\""
        if tag == "intro_pact":
            mod("trust_demon_lord", +20, 0, 100)
            st.flags["allied"] = True
            return f"You offer terms, not supplication. {dl} clasps your wrist. \"We hunt different prey—but we can share the trail.\""
        if tag == "intro_fight":
            mod("health", -15, 0, 100)
            mod("power", +5, 0, 100)
            mod("trust_demon_lord", +10, 0, 100)  # Respect through defiance
            return f"Steel rings. You draw blood and pay in kind. {dl} laughs like thunder far away. \"Live, then. Earn the right to stand.\""

        # Camp
        if tag == "camp_confide":
            mod("morality", +5, -100, 100)
            mod("trust_demon_lord", +12, 0, 100)
            return f"Your memory is a splinter. You let it out. {dl} listens without mercy—without judgment. The fire warms, just a little."
        if tag == "camp_silence":
            mod("power", +5, 0, 100); mod("trust_demon_lord", +2, 0, 100)
            return "You sharpen steel and silence. Sparks chart constellations no map has named."
        if tag == "camp_probe":
            mod("trust_demon_lord", -3, 0, 100); mod("notoriety", +5, 0, 100)
            return f"Questions are knives. {dl} answers some and turns aside others. You learn enough to be wary—and useful."
        if tag == "camp_scout":
            mod("power", +3, 0, 100); mod("health", +3, 0, 100)
            return "You pace the warding ring. Footprints. A bent reed. The forest is a chessboard and you are learning the moves."

        # Training
        if tag == "train_defense":
            mod("power", +7, 0, 100); mod("morality", +5, -100, 100); mod("trust_demon_lord", +5, 0, 100)
            return "Your ward blooms like a quiet star. It holds when claws descend. Somewhere, someone will live because of this."
        if tag == "train_wrath":
            mod("power", +12, 0, 100); mod("morality", -6, -100, 100); mod("notoriety", +6, 0, 100)
            return "You inhale the storm and exhale ruin. The stones remember your name as a crack."
        if tag == "train_sync":
            mod("power", +6, 0, 100); mod("trust_demon_lord", +10, 0, 100); st.bond_demon_lord = self.clamp(st.bond_demon_lord + 1, 0, 100)
            return f"Step, strike, breathe—together. {dl}'s motion becomes a language you begin to read."

        # Council
        if tag == "council_diplomacy":
            mod("morality", +8, -100, 100); mod("trust_demon_lord", +6, 0, 100)
            st.flags["seeking_truth"] = True
            return "You chart a path of proof and patience. The hall quiets; even war can listen."
        if tag == "council_raids":
            mod("power", +8, 0, 100); mod("notoriety", +10, 0, 100); st.flags["vow_revenge"] = True
            return "Targets line the map like sins. You thread a needle through them made of fire."
        if tag == "council_parley":
            mod("morality", +3, -100, 100); mod("notoriety", +3, 0, 100); st.flags["parley_set"] = True
            return "A secret parley—dangerous, delicate. If it holds, the story changes."

        # Oath
        if tag == "oath_sworn":
            mod("trust_demon_lord", +20, 0, 100); st.flags["oath_bound"] = True; st.bond_demon_lord = self.clamp(st.bond_demon_lord + 3, 0, 100)
            return "You swear by fang and star. The Moonwell seals the promise with a chill that tastes like dawn."
        if tag == "oath_hesitate":
            mod("trust_demon_lord", -5, 0, 100)
            return "You ask for time. The Moonwell reflects two strangers trying to be allies."
        if tag == "oath_refuse":
            mod("trust_demon_lord", -12, 0, 100); st.flags["allied"] = False
            return "You step back from the brink. Freedom is a lonely country."

        # Spies & Ambush
        if tag == "spy_intercept":
            mod("morality", +4, -100, 100); mod("notoriety", +5, 0, 100)
            return "You unmask the trap and free the bait. Rumors begin to turn toward truth."
        if tag == "spy_reverse":
            mod("power", +7, 0, 100); mod("morality", -2, -100, 100); mod("notoriety", +9, 0, 100)
            return "Hunters become the hunted. The forest keeps your secrets."
        if tag == "spy_ignore":
            mod("power", +4, 0, 100); mod("morality", -4, -100, 100)
            return "You let the game play on without you—for now."

        if tag == "ambush_shadow":
            mod("power", +8, 0, 100); mod("morality", -6, -100, 100); mod("notoriety", +8, 0, 100)
            return "No witnesses. No mercy. The bridge remembers only silence."
        if tag == "ambush_capture":
            mod("morality", +6, -100, 100); mod("notoriety", +4, 0, 100)
            return "Under your blade, a scout chooses life—and answers. Names spill like beads from a torn chain."
        if tag == "ambush_letgo":
            mod("morality", +2, -100, 100); mod("notoriety", +6, 0, 100)
            return "Mercy travels faster than hoofbeats. Fear travels faster still."

        # Rescue
        if tag == "rescue_shield":
            mod("morality", +10, -100, 100); mod("health", -8, 0, 100); mod("trust_demon_lord", +4, 0, 100)
            return "You take the blows others could not bear. A child's cough becomes a laugh."
        if tag == "rescue_ruse":
            mod("morality", +6, -100, 100); mod("power", +3, 0, 100)
            return "Illusions, footprints, a staged cry—bandits chase ghosts while the caravan slips free."
        if tag == "rescue_walk":
            mod("morality", -10, -100, 100); mod("power", +4, 0, 100); mod("notoriety", +5, 0, 100)
            return "You turn away. The road learns your name without deciding if it loves you."

        # Grim bargain
        if tag == "bargain_memory":
            mod("power", +15, 0, 100); mod("morality", -8, -100, 100)
            st.history.append("You traded a cherished memory at the Thorn Altar.")
            return "You give the altar a memory of home. Power rushes in to fill the hollow it leaves."
        if tag == "bargain_reject":
            mod("morality", +5, -100, 100); mod("trust_demon_lord", +3, 0, 100)
            return "You walk away from easy strength. The altar hums, disappointed."
        if tag == "bargain_token":
            mod("power", +10, 0, 100); mod("notoriety", +7, 0, 100)
            return "You place a betrayer's token on the altar. The thorns drink deep and answer with power."

        # Ruins
        if tag == "ruins_study":
            mod("power", +4, 0, 100); mod("morality", +2, -100, 100)
            st.history.append("Discovered records of prior heroes consumed by their crowns.")
            return "Glyphs confess: heroes burned an age to keep a throne warm. Truth is an ember you pocket."
        if tag == "ruins_force":
            mod("power", +8, 0, 100); mod("morality", -4, -100, 100)
            st.inventory.append("Vault Relic"); st.inventory = list(dict.fromkeys(st.inventory))
            return "The vault yields with a scream of stone. Inside waits a relic that knows your pulse."
        if tag == "ruins_mark":
            mod("morality", +1, -100, 100); mod("trust_demon_lord", +2, 0, 100)
            return "You leave a mark, not a wound. Even ruins deserve a future."

        # Wild Hunt
        if tag == "hunt_race":
            mod("power", +5, 0, 100); mod("notoriety", +3, 0, 100)
            return "You run with ghosts until your lungs are bells. They teach you shortcuts through moonlight."
        if tag == "hunt_duel":
            mod("power", +10, 0, 100); mod("health", -6, 0, 100); mod("notoriety", +6, 0, 100)
            return "Steel rings against antler and oath. You win a scar and a salute."
        if tag == "hunt_hide":
            mod("morality", +2, -100, 100)
            return "You watch unseen as the Wild Hunt redraws the night's borders."

        # Whispers
        if tag == "whisper_follow":
            mod("notoriety", +4, 0, 100)
            st.flags["betrayer_trail"] = True
            return "The whisper leads to a sigil cut in bark: a hero's mark. The trail warms under your gaze."
        if tag == "whisper_ward":
            mod("power", +3, 0, 100); mod("morality", +1, -100, 100)
            return "You hush the forest with a ward that tastes like peppermint and thunder."
        if tag == "whisper_together":
            mod("trust_demon_lord", +8, 0, 100); st.bond_demon_lord = self.clamp(st.bond_demon_lord + 1, 0, 100)
            return f"You and {dl} listen as one. The voices braid into a map only two can read."

        # Unknown tag fallback
        return "Time moves, yet nothing decisive happens. Perhaps the next choice will cut deeper."

    # ----- Ending checks -----
    def check_ending(self, st: StoryState) -> Optional[str]:
        """Return ending text if conditions met, else None."""
        dl = st.flags.get("demon_lord_name", "the Demon Lord")
        if st.health <= 0:
            return "Your story ends beneath black boughs. Even the forest bows its head."
        # Ascendant Alliance
        if st.trust_demon_lord >= 80 and st.power >= 70 and st.flags.get("oath_bound"):
            return (f"Side by side with {dl}, you confront the crown. Proof and power make a quiet revolution.\n"
                    "The heroes who betrayed you kneel, not to force, but to truth. The forest grows less afraid.")
        # Lone Sovereign
        if st.notoriety >= 80 and st.power >= 80 and st.morality <= -30:
            return ("Feared and unstoppable, you become a storm that keeps its own counsel. Kings learn to read the sky.")
        # Redeemed Guardian
        if st.morality >= 80 and st.power >= 50:
            return ("You choose to guard rather than rule. Roads are safer where your shadow falls.")
        # Quiet Exile
        if st.chapter >= 30 and st.trust_demon_lord < 40 and st.notoriety < 40:
            return ("Years pass like leaves. Your name fades, but the people you saved remember.\n"
                    "Not all legends need thrones.")
        # No ending yet
        return None

# ---------- IO & Game Loop ----------

def prompt(msg: str) -> str:
    try:
        return input(msg)
    except EOFError:
        return "quit"

def print_stats(st: StoryState):
    print("\n--- Stats ---")
    print(f"Name: {st.name} | Chapter: {st.chapter} | Location: {st.location}")
    print(f"Health: {st.health}  Power: {st.power}  Morality: {st.morality}  Notoriety: {st.notoriety}")
    print(f"Trust (Demon Lord): {st.trust_demon_lord}  Bond: {st.bond_demon_lord}")
    print(f"Inventory: {', '.join(st.inventory) if st.inventory else '(empty)'}")
    if st.flags:
        key_flags = [k for k, v in st.flags.items() if v]
        if key_flags:
            print(f"Notable Flags: {', '.join(sorted(key_flags))}")
    print("-------------\n")

def show_help():
    print(dedent("""
    Commands you can type anytime:
      help           - show this help
      stats          - show your current stats
      save <slot>    - save to slot 1-8 (e.g., save 3)
      load <slot>    - load from slot 1-8 (e.g., load 2)
      slots          - list existing saves
      quit           - exit the game
    """))

def parse_command(s: str) -> Tuple[str, Optional[int]]:
    parts = s.strip().lower().split()
    if not parts:
        return "", None
    if parts[0] in {"help","stats","slots","quit"}:
        return parts[0], None
    if parts[0] in {"save", "load"}:
        if len(parts) >= 2 and parts[1].isdigit():
            return parts[0], int(parts[1])
        else:
            return parts[0], None
    return "", None

def game_loop(state: StoryState):
    rng = random.Random(state.seed)
    engine = StoryEngine(rng)
    saver = SaveManager()

    print(ascii_title())
    print("You can type 'help' at any time.\n")
    show_help()

    while True:
        # Endings?
        ending = engine.check_ending(state)
        if ending:
            print("\n=== An Ending Unfolds ===")
            print(ending)
            print("\nThanks for playing A Game Of Lore.\n")
            return

        # Generate scene
        text, choices = engine.generate_scene(state)
        print(f"\n[Chapter {state.chapter}] {state.location}")
        print("\n" + text + "\n")

        # Display choices
        for i, (ctext, _) in enumerate(choices, start=1):
            print(f"  {i}. {ctext}")
        print("  (Or type a command: save <n>, load <n>, stats, slots, help, quit)")

        # Read input
        while True:
            raw = prompt("\nYour choice: ").strip()
            cmd, slot = parse_command(raw)
            if cmd:
                if cmd == "help":
                    show_help()
                    continue
                if cmd == "stats":
                    print_stats(state); continue
                if cmd == "slots":
                    saves = saver.list_saves()
                    if not saves:
                        print("No saves yet. Use: save <slot> (1-8)")
                    else:
                        print("Existing saves:")
                        for s, ts in saves:
                            print(f"  Slot {s}: {ts}")
                    continue
                if cmd == "quit":
                    print("Farewell, traveler.")
                    return
                if cmd == "save":
                    if slot is None:
                        print("Usage: save <slot number 1-8>"); continue
                    try:
                        path = saver.save(slot, state)
                        print(f"Saved to Slot {slot} ({path})")
                    except Exception as e:
                        print(f"Save failed: {e}")
                    continue
                if cmd == "load":
                    if slot is None:
                        print("Usage: load <slot number 1-8>"); continue
                    try:
                        state = saver.load(slot)
                        rng.seed(state.seed)
                        print(f"Loaded Slot {slot}.")
                        print_stats(state)
                    except Exception as e:
                        print(f"Load failed: {e}")
                    continue

            # Not a command: try numeric choice
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(choices):
                    _, tag = choices[idx - 1]
                    follow = engine.apply_choice(state, tag)
                    print("\n" + follow + "\n")
                    # Incidental attr drift to keep story lively
                    if engine._p(0.15):
                        state.health = engine.clamp(state.health + rng.choice([-2, -1, +1, +2]), 0, 100)
                    break
                else:
                    print("Pick a listed choice number.")
            else:
                print("Type a choice number, or a command like 'save 1' or 'help'.")

def new_game() -> StoryState:
    print(ascii_title())
    print("Welcome to A Game Of Lore.\n")
    name = input("What name shall your legend carry? ").strip()
    if not name:
        name = "Nameless"
    # Deterministic-ish seed from name + time
    seed_src = f"{name}-{time.time()}".encode("utf-8")
    seed = int(hashlib.sha256(seed_src).hexdigest(), 16) % (2**32)
    st = StoryState(name=name, seed=seed)
    st.flags = {
        "betrayed": True,
        "met_demon_lord": True,
        "allied": False,
        "seeking_truth": True,
    }
    return st

def main():
    saver = SaveManager()
    while True:
        print(ascii_title())
        print("1) New Game")
        print("2) Load Game")
        print("3) Quit")
        choice = input("\nSelect: ").strip()
        cl = choice.strip().lower()
        if cl in ("1", "n", "new", "new game"):
            state = new_game()
            game_loop(state)
        elif cl in ("2", "l", "load", "load game"):
            print("Enter slot number (1-8): ", end="")
            slot = input().strip()
            if slot.isdigit():
                try:
                    state = saver.load(int(slot))
                    game_loop(state)
                except Exception as e:
                    print(f"Could not load: {e}")
                    input("Press Enter to continue...")
            else:
                print("Invalid slot.")
        elif cl in ("3", "q", "quit", "exit"):
            print("Goodbye.")
            return
        else:
            print("Please choose 1, 2, or 3.\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting. Your legend rests—for now.")
