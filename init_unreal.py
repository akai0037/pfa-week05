# Runs automatically when any Unreal Editor project starts (with the Python plugin enabled).
import unreal

try:
    import claude_bridge
    claude_bridge.start()
except Exception as e:
    unreal.log_warning("[claude_bridge] failed to start: %s" % e)
