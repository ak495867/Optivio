from optivio_desktop.app import OptivioConsole

app = OptivioConsole()
assert app.title().startswith("Optivio")
assert app.component_tree.exists("point_in_time")
app.orchestrator.invoke("point_in_time")
app.destroy()
print("tkinter-smoke-ok")
