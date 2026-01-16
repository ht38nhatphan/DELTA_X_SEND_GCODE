import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from PyQt5.QtCore import QObject, pyqtSignal, QTimer


@dataclass
class CallFrame:
    return_index: int
    return_scope: str
    sub_name: int
    repeat_left: int
    sub_first_exec_index: int


Number = Union[int, float]


class MacroRunner(QObject):
    """
    PC-side macro interpreter with 'ok' handshake.

    PC-interpreted features:
      - N labels: N10 ...
      - Variables: #100, #101 ...
      - Assignments: #100 = #100 + 1
      - IF [cond] THEN GOTO <N>     (local evaluate + local jump)
      - Subprogram blocks: O#### ... M99
      - Subprogram call: M98 P#### [L<count>]  (local call stack)
      - Return: M99

    Sent to controller:
      - Real motion/commands lines (G0/G1/M... etc) that are not macro-control.
    """

    command_to_send = pyqtSignal(str)
    log_message = pyqtSignal(str)
    current_line_changed = pyqtSignal(int)
    finished = pyqtSignal()

    # ---------------- Regex ----------------
    _re_block_comment = re.compile(r"\([^)]*\)")  # remove (...) blocks on same line
    _re_leading_n = re.compile(r"^\s*N(\d+)\b", re.IGNORECASE)
    _re_o_sub = re.compile(r"^\s*O(\d+)\s*$", re.IGNORECASE)

    _re_uncond_goto = re.compile(r"^\s*GOTO\s+(\d+)\s*$", re.IGNORECASE)
    _re_if_then = re.compile(r"^\s*IF\s*\[(.+?)\]\s*THEN\s*(.+)\s*$", re.IGNORECASE)

    # M98 P1000  OR  M98 P1000 L3
    _re_m98 = re.compile(r"^\s*M98\s+P(\d+)(?:\s+L(\d+))?\s*$", re.IGNORECASE)
    _re_m99 = re.compile(r"^\s*M99\b", re.IGNORECASE)

    # Assignment: #100 = expr
    _re_assign = re.compile(r"^\s*#([A-Za-z_][\w\.]*|\d+)\s*=\s*(.+?)\s*$", re.IGNORECASE)

    # Condition operators (Delta macro style)
    _cond_ops = ("EQ", "NE", "GT", "GE", "LT", "LE")

    # Tokenizer for arithmetic expressions (numbers, #vars, operators, parentheses)
    _re_token = re.compile(r"""
        \s*(
            \#[A-Za-z_][\w\.]* |  # variable name  #Counter or #robot0.HOME_Z
            \#\d+              |  # variable number #100
            \d+(?:\.\d+)?      |  # number
            [+\-*/()]          |
            \bMOD\b            |
            .
        )
    """, re.IGNORECASE | re.VERBOSE)

    def __init__(self):
        super().__init__()

        self.lines: List[str] = []
        self.is_running: bool = False
        self.waiting_for_ok: bool = False
        self.debug_mode: bool = False

        self.current_index: int = 0
        self.current_scope: str = "MAIN"  # "MAIN" or "O####"

        # Variables: #100, #101 ...
        # Variables: #100, #101 ...
        self.vars: Dict[int, float] = {}
        self.named_vars: Dict[str, int] = {}
        self._next_named_var = 1000
        
        # Machine Position (System Variables)
        self.machine_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        self.sys_vars_map = {
            "ROBOT0.HOME_X": -1,
            "ROBOT0.HOME_Y": -2,
            "ROBOT0.HOME_Z": -3
        }

        # Label maps: scope -> {N: line_index}
        self.label_maps: Dict[str, Dict[int, int]] = {"MAIN": {}}

        # Subprogram table: sub_name -> (o_line_index, first_exec_index, end_m99_index)
        self.subprograms: Dict[int, Tuple[int, int, int]] = {}

        # Call stack
        self.call_stack: List[CallFrame] = []
        

        # Watchdog
        self.watchdog = QTimer()
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self.on_watchdog_timeout)
        self.watchdog_timeout_ms = 5000
    def set_speed_override(self, factor: float):
        self.speed_override = factor
        self.log_message.emit(f"Speed override set to {factor*100:.0f}%")

    def _resolve_var(self, token: str) -> int:
        # #100
        if token[1:].isdigit():
            return int(token[1:])

        # #Counter or #robot0.HOME_Z
        name = token[1:].upper()
        
        if name in self.sys_vars_map:
            return self.sys_vars_map[name]
            
        if name not in self.named_vars:
            self.named_vars[name] = self._next_named_var
            self._next_named_var += 1
        return self.named_vars[name]
        
    def update_machine_position(self, x: float, y: float, z: float):
        self.machine_pos['X'] = x
        self.machine_pos['Y'] = y
        self.machine_pos['Z'] = z

    # ---------------- Text utilities ----------------
    def strip_comments(self, line: str) -> str:
        """
        Remove:
          - anything after ';'
          - inline block comments '(...)'
        """
        if not line:
            return ""
        semi = line.find(';')
        if semi != -1:
            line = line[:semi]
        line = self._re_block_comment.sub("", line)
        return line.strip()

    def normalize_spacing(self, line: str) -> str:
        """
        Gentle normalization:
          - IF[  -> IF [
          - ]THEN -> ] THEN
        Do NOT attempt to rewrite inside-condition spacing aggressively.
        """
        s = line
        s = re.sub(r"\bIF\s*\[", "IF [", s, flags=re.IGNORECASE)
        s = re.sub(r"\]\s*THEN\b", "] THEN", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def preprocess_line(self, raw_line: str) -> str:
        cleaned = self.strip_comments(raw_line)
        if not cleaned:
            return ""
        return self.normalize_spacing(cleaned)

    def split_leading_n(self, line: str) -> Tuple[Optional[int], str]:
        """
        If line starts with Nxx, return (xx, rest_without_Nxx).
        """
        m = self._re_leading_n.match(line)
        if not m:
            return None, line.strip()
        n_val = int(m.group(1))
        rest = line[m.end():].strip()
        return n_val, rest

    # ---------------- Parsing ----------------
    def parse_script(self, script_text: str):
        self.lines = script_text.splitlines()

        self.label_maps = {"MAIN": {}}
        self.subprograms = {}
        self.call_stack = []
        self.current_scope = "MAIN"

        # Variables reset each run (you can keep if you want persistent)
        self.vars = {}

        # 1) Identify subprogram blocks O#### ... M99
        idx = 0
        while idx < len(self.lines):
            line = self.preprocess_line(self.lines[idx]).upper()
            
            # Strip N number if present (e.g. N40 O2000)
            _n, rest_line = self.split_leading_n(line)
            
            m_o = self._re_o_sub.match(rest_line)
            if m_o:
                sub_name = int(m_o.group(1))
                o_line_index = idx
                first_exec_index = min(idx + 1, len(self.lines))

                end_idx = None
                j = idx + 1
                while j < len(self.lines):
                    lj = self.preprocess_line(self.lines[j]).upper()
                    
                    # Strip N number for end check too (e.g. N75 M99)
                    _nj, rest_j = self.split_leading_n(lj)
                    
                    if self._re_o_sub.match(rest_j):  # nested O before M99 -> malformed
                        break
                    if self._re_m99.match(rest_j):
                        end_idx = j
                        break
                    j += 1

                if end_idx is None:
                    end_idx = len(self.lines) - 1

                self.subprograms[sub_name] = (o_line_index, first_exec_index, end_idx)
                self.label_maps[f"O{sub_name}"] = {}

                idx = end_idx + 1
                continue

            idx += 1

        # 2) Build label maps by scope
        scope_by_line = ["MAIN"] * len(self.lines)
        for sub_name, (o_idx, _, end_idx) in self.subprograms.items():
            scope = f"O{sub_name}"
            for k in range(o_idx, end_idx + 1):
                scope_by_line[k] = scope

        for i, raw in enumerate(self.lines):
            cleaned = self.preprocess_line(raw)
            if not cleaned:
                continue
            scope = scope_by_line[i]
            # Map N labels
            n, _rest = self.split_leading_n(cleaned.upper())
            if n is not None:
                self.label_maps.setdefault(scope, {})[n] = i

    # ---------------- Control ----------------
    def start_macro(self, script_text: str, is_debug: bool = False):
        if self.is_running:
            return

        self.parse_script(script_text)
        if not self.lines:
            self.log_message.emit("Macro is empty.")
            return

        self.is_running = True
        self.debug_mode = is_debug
        self.waiting_for_ok = False

        self.current_index = 0
        self.current_scope = "MAIN"
        self.call_stack = []

        mode_str = "DEBUG MODE" if is_debug else "NORMAL RUN"
        self.log_message.emit(f"--- MACRO STARTED ({mode_str}) ---")

        if self.debug_mode:
            self.log_message.emit("Paused. Press 'STEP' to execute line 0.")
            self.current_line_changed.emit(self.current_index)
            return

        self.run_current_line()

    def step(self):
        if not self.is_running:
            return
        if self.waiting_for_ok:
            self.log_message.emit("Waiting for 'ok' from controller...")
            return
        self.run_current_line()

    def stop_macro(self):
        self.is_running = False
        self.debug_mode = False
        self.waiting_for_ok = False
        self.watchdog.stop()
        self.call_stack.clear()
        self.log_message.emit("--- MACRO STOPPED ---")
        self.finished.emit()

    # ---------------- Execution helpers ----------------
    def _advance(self, next_index: int, next_scope: Optional[str] = None):
        self.current_index = next_index
        if next_scope is not None:
            self.current_scope = next_scope

        if self.current_index >= len(self.lines):
            self.stop_macro()
            return

        self.current_line_changed.emit(self.current_index)

        if self.debug_mode:
            self.log_message.emit("Debug: Ready. Press 'STEP' to execute.")
            return

        QTimer.singleShot(0, self.run_current_line)

    def _send_and_wait_ok(self, line: str):
        self.waiting_for_ok = True
        self.command_to_send.emit(line)
        self.watchdog.start(self.watchdog_timeout_ms)

    # ---------------- Expression evaluation ----------------
    def get_var(self, var_num: int) -> float:
        if var_num == -1: return self.machine_pos['X']
        if var_num == -2: return self.machine_pos['Y']
        if var_num == -3: return self.machine_pos['Z']
        return float(self.vars.get(var_num, 0.0))

    def set_var(self, var_num: int, value: Number):
        self.vars[var_num] = float(value)

    def _tokenize_expr(self, expr: str) -> List[str]:
        tokens: List[str] = []
        for m in self._re_token.finditer(expr):
            t = m.group(1)
            if not t:
                continue
            t = t.strip()
            if not t:
                continue
            tokens.append(t)
        return tokens

    def _to_rpn(self, tokens: List[str]) -> List[str]:
        """
        Shunting-yard to convert to Reverse Polish Notation.
        Supports + - * / MOD and parentheses.
        """
        out: List[str] = []
        stack: List[str] = []

        prec = {
            "MOD": 2,
            "*": 2,
            "/": 2,
            "+": 1,
            "-": 1,
        }

        def is_op(tok: str) -> bool:
            return tok.upper() in prec

        for tok in tokens:
            up = tok.upper()

            # variable (named or numbered)
            if tok.startswith("#"):
                out.append(tok)
                continue
            
            # number (restore removed check)
            if re.match(r"^\d+(\.\d*)?$", tok) or re.match(r"^\.\d+$", tok):
                out.append(tok)
                continue

            if up == "(":
                stack.append(up)
                continue
            if up == ")":
                while stack and stack[-1] != "(":
                    out.append(stack.pop())
                if stack and stack[-1] == "(":
                    stack.pop()
                else:
                    raise ValueError("Mismatched parentheses")
                continue

            if is_op(up):
                while stack and stack[-1] in prec and prec[stack[-1]] >= prec[up]:
                    out.append(stack.pop())
                stack.append(up)
                continue

            # Unknown token => error
            raise ValueError(f"Unknown token in expression: '{tok}'")

        while stack:
            op = stack.pop()
            if op in ("(", ")"):
                raise ValueError("Mismatched parentheses")
            out.append(op)

        return out

    def eval_arith(self, expr: str) -> float:
        tokens = self._tokenize_expr(expr)
        # Handle unary minus by inserting 0 before leading '-' or after '('
        fixed: List[str] = []
        prev = None
        for t in tokens:
            if t == "-" and (prev is None or prev in ("(", "+", "-", "*", "/", "MOD")):
                fixed.extend(["0", "-"])
            else:
                fixed.append(t)
            prev = t.upper() if isinstance(t, str) else t

        rpn = self._to_rpn(fixed)
        st: List[float] = []

        for tok in rpn:
            up = tok.upper()
            
            # Variable resolution (numbered or named)
            if tok.startswith("#"):
                var_num = self._resolve_var(tok)
                st.append(self.get_var(var_num))
            
            # Number
            elif re.match(r"^\d+(\.\d*)?$", tok) or re.match(r"^\.\d+$", tok):
                st.append(float(tok))
                
            elif up in ("+", "-", "*", "/", "MOD"):
                if len(st) < 2:
                    raise ValueError("Bad expression stack")
                b = st.pop()
                a = st.pop()
                if up == "+":
                    st.append(a + b)
                elif up == "-":
                    st.append(a - b)
                elif up == "*":
                    st.append(a * b)
                elif up == "/":
                    st.append(a / b)
                elif up == "MOD":
                    st.append(a % b)
            else:
                raise ValueError(f"Bad RPN token: {tok}")

        if len(st) != 1:
            raise ValueError("Bad expression result")
        return float(st[0])

    def eval_condition(self, cond: str) -> bool:
        """
        Supports:
          - <expr> OP <expr> where OP in EQ NE GT GE LT LE
          - Combine with AND / OR (left-to-right)
        Example:
          "#100 LE 2"
          "[#100 GE 1] AND [#101 LT 3]"  (outer brackets already stripped by IF parser)
        """
        # Normalize spaces
        c = re.sub(r"\s+", " ", cond.strip())

        # Split OR first
        or_parts = re.split(r"\bOR\b", c, flags=re.IGNORECASE)
        or_results: List[bool] = []
        for part in or_parts:
            part = part.strip()
            if not part:
                continue
            and_parts = re.split(r"\bAND\b", part, flags=re.IGNORECASE)
            and_ok = True
            for ap in and_parts:
                ap = ap.strip()
                if not ap:
                    continue
                and_ok = and_ok and self._eval_simple_comparison(ap)
                if not and_ok:
                    break
            or_results.append(and_ok)

        return any(or_results) if or_results else False

    def _eval_simple_comparison(self, text: str) -> bool:
        """
        Supports:
        EQ NE GT GE LT LE
        <  >  <=  >=
        """
        t = re.sub(r"\s+", " ", text.strip())

        # Normalize symbolic operators to word operators
        replacements = {
            "<=": " LE ",
            ">=": " GE ",
            "==": " EQ ",
            "!=": " NE ",
            "<": " LT ",
            ">": " GT ",
        }

        for k, v in replacements.items():
            t = t.replace(k, v)

        # Find operator
        op_found = None
        for op in self._cond_ops:
            if re.search(rf"\b{op}\b", t, flags=re.IGNORECASE):
                op_found = op
                break

        if not op_found:
            raise ValueError(
                f"Condition missing operator (EQ/NE/GT/GE/LT/LE): '{text}'"
            )

        left, right = re.split(
            rf"\b{op_found}\b", t, maxsplit=1, flags=re.IGNORECASE
        )

        a = self.eval_arith(left.strip())
        b = self.eval_arith(right.strip())

        if op_found == "EQ":
            return a == b
        if op_found == "NE":
            return a != b
        if op_found == "GT":
            return a > b
        if op_found == "GE":
            return a >= b
        if op_found == "LT":
            return a < b
        if op_found == "LE":
            return a <= b

        raise ValueError(f"Unknown operator: {op_found}")

    # ---------------- Main runner ----------------
    def run_current_line(self):
        if not self.is_running:
            return
        if self.current_index >= len(self.lines):
            self.stop_macro()
            return

        raw_line = self.lines[self.current_index]
        line = self.preprocess_line(raw_line)

        # UI update even for blanks
        self.current_line_changed.emit(self.current_index)

        if not line:
            self._advance(self.current_index + 1, self.current_scope)
            return

        u = line.upper()

        # Split leading N (keep for label map, but execution uses 'rest')
        _n, rest = self.split_leading_n(line)
        u_rest = rest.upper()

        # 0) Subprogram header O####
        # Fix: If we hit an O-line, it means we 'fell through' to it (since M98 jumps to body).
        # We should skip the entire block.
        m_o = self._re_o_sub.match(u_rest)
        if m_o:
            sub_name = int(m_o.group(1))
            if sub_name in self.subprograms:
                _, _, end_idx = self.subprograms[sub_name]
                self.log_message.emit(f"Skipping subprogram O{sub_name} definition.")
                self._advance(end_idx + 1, self.current_scope)
            else:
                # Should not happen if parse_script works, but safety fallback
                self._advance(self.current_index + 1, self.current_scope)
            return

        # 1) Assignment: #100 = expr  (LOCAL)
        m_as = self._re_assign.match(u_rest)
        if m_as:
            var_token = "#" + m_as.group(1)
            var_num = self._resolve_var(var_token)
            expr = m_as.group(2)
            try:
                val = self.eval_arith(expr)
                self.set_var(var_num, val)
                self.log_message.emit(f"Set #{var_num} = {val:g}")
            except Exception as e:
                self.log_message.emit(f"Assignment error at line {self.current_index}: {e}")
                self.stop_macro()
                return

            self._advance(self.current_index + 1, self.current_scope)
            return

        # 2) IF [cond] THEN action  (LOCAL EVAL)
        m_if = self._re_if_then.match(u_rest)
        if m_if:
            cond = m_if.group(1).strip()
            action = m_if.group(2).strip()

            try:
                ok = self.eval_condition(cond)
            except Exception as e:
                self.log_message.emit(f"IF parse/eval error at line {self.current_index}: {e}")
                self.stop_macro()
                return

            if ok:
                # Support THEN GOTO N  (LOCAL JUMP)
                m_g = self._re_uncond_goto.match(action)
                if m_g:
                    target_n = int(m_g.group(1))

                    # Jump preference: MAIN labels if we're in MAIN loop
                    # For your loop example, it must jump inside MAIN.
                    main_map = self.label_maps.get("MAIN", {})
                    if target_n in main_map:
                        target_idx = main_map[target_n]
                        self.log_message.emit(f"IF true -> GOTO N{target_n} (MAIN)")
                        self._advance(target_idx, "MAIN")
                        return

                    # fallback current scope labels
                    scope_map = self.label_maps.get(self.current_scope, {})
                    if target_n in scope_map:
                        target_idx = scope_map[target_n]
                        self.log_message.emit(f"IF true -> GOTO N{target_n} ({self.current_scope})")
                        self._advance(target_idx, self.current_scope)
                        return

                    self.log_message.emit(f"IF GOTO Error: Label N{target_n} not found!")
                    self.stop_macro()
                    return

                # If action not supported locally, you can either:
                # - send to controller, OR
                # - treat as error
                self.log_message.emit(f"IF action not supported locally: '{action}'")
                self.stop_macro()
                return
            else:
                # IF false -> just go next line
                self._advance(self.current_index + 1, self.current_scope)
                return

        # 3) M98 call (LOCAL)
        m98 = self._re_m98.match(u_rest)
        if m98:
            sub_name = int(m98.group(1))
            repeat = int(m98.group(2)) if m98.group(2) else 1
            if repeat <= 0:
                repeat = 1

            if sub_name not in self.subprograms:
                self.log_message.emit(f"Call Error: O{sub_name} not found for '{rest}'")
                self.stop_macro()
                return

            _, first_exec, _end_idx = self.subprograms[sub_name]

            self.call_stack.append(
                CallFrame(
                    return_index=self.current_index + 1,
                    return_scope=self.current_scope,
                    sub_name=sub_name,
                    repeat_left=repeat,
                    sub_first_exec_index=first_exec,
                )
            )

            self.log_message.emit(f"Calling subprogram O{sub_name} (x{repeat})")
            self._advance(first_exec, f"O{sub_name}")
            return

        # 4) M99 return (LOCAL)
        if self._re_m99.match(u_rest):
            if not self.call_stack:
                self.log_message.emit("M99 encountered with empty call stack. Stopping.")
                self.stop_macro()
                return

            frame = self.call_stack[-1]
            if frame.repeat_left > 1:
                frame.repeat_left -= 1
                self.call_stack[-1] = frame
                self.log_message.emit(f"Repeating O{frame.sub_name} (remaining {frame.repeat_left})")
                self._advance(frame.sub_first_exec_index, f"O{frame.sub_name}")
                return

            self.call_stack.pop()
            self.log_message.emit(f"Return from O{frame.sub_name}")
            self._advance(frame.return_index, frame.return_scope)
            return

        # 5) Unconditional GOTO N (LOCAL)
        mg = self._re_uncond_goto.match(u_rest)
        if mg:
            target_n = int(mg.group(1))
            # Prefer current scope then MAIN
            scope_map = self.label_maps.get(self.current_scope, {})
            if target_n in scope_map:
                self.log_message.emit(f"GOTO N{target_n} ({self.current_scope})")
                self._advance(scope_map[target_n], self.current_scope)
                return
            main_map = self.label_maps.get("MAIN", {})
            if target_n in main_map:
                self.log_message.emit(f"GOTO N{target_n} (MAIN)")
                self._advance(main_map[target_n], "MAIN")
                return

            self.log_message.emit(f"GOTO Error: Label N{target_n} not found!")
            self.stop_macro()
            return

        # 6) Otherwise: send to controller and wait ok
        # Fix: Substitute variables first! e.g. G01 Z[#100 + 10] -> G01 Z110
        try:
            final_cmd = self.substitute_vars(rest)
            
            # Apply Speed Override to Feed Rate (F)
            if self.speed_override != 1.0:
                # Regex to find F<val>, e.g. F1000 or F 1000
                # We use a replacer function to scale the value
                def f_replacer(match):
                    prefix = match.group(1) # F
                    val = float(match.group(2))
                    new_val = val * self.speed_override
                    return f"{prefix}{new_val:.2f}"
                
                final_cmd = re.sub(r"([Ff])\s*(\d+(?:\.\d+)?)", f_replacer, final_cmd)

            self._send_and_wait_ok(final_cmd)
        except Exception as e:
            self.log_message.emit(f"Substitution/Eval Error at line {self.current_index}: {e}")
            self.stop_macro()
            return

    def substitute_vars(self, line: str) -> str:
        """
        Replace [expr] blocks with evaluated result.
        Also handles standalone #vars if needed, but typically standard G-code uses [] for expressions.
        However, pure #100 replacement might be useful too.
        Let's stick to [] for now as per user request: Z[#robot0.HOME_Z - 80]
        """
        # Regex to find [...]
        pattern = re.compile(r"\[(.*?)\]")
        
        def replacer(match):
            expr = match.group(1)
            val = self.eval_arith(expr)
            # Format: .3f or similar? G-code usually expects reasonable precision.
            # %g removes trailing zeros
            return f"{val:g}"

        return pattern.sub(replacer, line)

    # ---------------- Serial RX ----------------
    def on_serial_rx(self, message: str):
        print(message)
        if not self.is_running or not self.waiting_for_ok:
            return
        
        if "ok" in (message or "").lower():
            self.waiting_for_ok = False
            self.watchdog.stop()

            self.current_index += 1
            if self.current_index >= len(self.lines):
                self.stop_macro()
                return

            if self.debug_mode:
                self.log_message.emit(f"Debug: Line finished. Next line: {self.current_index}")
                self.current_line_changed.emit(self.current_index)
                return

            QTimer.singleShot(0, self.run_current_line)

    def on_watchdog_timeout(self):
        if self.is_running and self.waiting_for_ok:
            self.log_message.emit("Timeout requesting 'ok' response. Stopping macro.")
            self.stop_macro()
