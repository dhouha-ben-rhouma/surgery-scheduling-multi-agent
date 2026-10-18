import os
import shutil

dirs = ["orchestrator", "tools", "tests", "gui", "logs"]
for d in dirs:
    os.makedirs(d, exist_ok=True)

moves = {
    "agent.py": "orchestrator/agent.py",
    "planner.py": "orchestrator/planner.py",
    "scenario.py": "orchestrator/scenario.py",
    "failure_config.py": "orchestrator/failure_config.py",
    "cache_stats.py": "orchestrator/cache_stats.py",
    "tools.py": "tools/tools.py",
    "tests.py": "tests/tests.py",
    "test_concurrency.py": "tests/test_concurrency.py",
    "app.py": "gui/app.py",
    "gui.py": "gui/gui.py",
}

for src, dst in moves.items():
    if os.path.exists(src):
        shutil.move(src, dst)

# Create init files
with open("orchestrator/__init__.py", "w") as f: f.write("")
with open("tools/__init__.py", "w") as f:
    f.write("from .tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS\n")
with open("gui/__init__.py", "w") as f: f.write("")
with open("tests/__init__.py", "w") as f: f.write("")

# Fix imports in orchestrator/agent.py
with open("orchestrator/agent.py", "r") as f: content = f.read()
content = content.replace("from tools import", "from tools.tools import")
content = content.replace("from planner import", "from .planner import")
with open("orchestrator/agent.py", "w") as f: f.write(content)

# Fix imports in orchestrator/planner.py
with open("orchestrator/planner.py", "r") as f: content = f.read()
content = content.replace("from tools import", "from tools.tools import")
content = content.replace("from cache_stats import", "from .cache_stats import")
with open("orchestrator/planner.py", "w") as f: f.write(content)

# Fix imports in orchestrator/scenario.py
if os.path.exists("orchestrator/scenario.py"):
    with open("orchestrator/scenario.py", "r") as f: content = f.read()
    content = content.replace("from agent import", "from .agent import")
    content = content.replace("from planner import", "from .planner import")
    content = content.replace("from failure_config import", "from .failure_config import")
    with open("orchestrator/scenario.py", "w") as f: f.write(content)

# Fix imports in gui/app.py
if os.path.exists("gui/app.py"):
    with open("gui/app.py", "r") as f: content = f.read()
    content = content.replace("from scenario import", "from orchestrator.scenario import")
    with open("gui/app.py", "w") as f: f.write(content)

# Fix imports in gui/gui.py
if os.path.exists("gui/gui.py"):
    with open("gui/gui.py", "r") as f: content = f.read()
    content = content.replace("from scenario import", "from orchestrator.scenario import")
    with open("gui/gui.py", "w") as f: f.write(content)
