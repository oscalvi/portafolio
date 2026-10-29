"""Respuestas de ejemplo para estudiar cada pregunta de la entrevista virtual (sin IA).

Las técnicas son respuestas modelo fijas. Las personales usan una línea real de la hoja de vida
del candidato ({logro}) en primera persona y la estructura STAR; las partes entre [corchetes]
son para que el candidato las complete con sus datos. Nunca se inventa experiencia.
"""
import re

MODELOS = {
    # ---------------- Apertura ----------------
    "presentacion": {
        "en": "I'm {titular}. {perfil} One example I'm proud of: {logro}. Today I use AI coding tools every day to design, write and review code, "
              "and I know where they fail. That's why this {puesto} role fits me: it combines real software engineering with judging what good code looks like.",
        "es": "Soy {titular}. {perfil} Un ejemplo del que me siento orgulloso: {logro}. Hoy uso herramientas de IA para programar a diario, "
              "para diseñar, escribir y revisar código, y sé dónde fallan. Por eso esta posición de {puesto} encaja conmigo: combina ingeniería real "
              "con criterio sobre qué es buen código."},
    "por_que": {
        "en": "Two reasons. First, the work itself: {empresa} needs engineers who can take a real change and turn it into a fair, hard task, and that's "
              "exactly the kind of analysis I've done for years. Second, the timing: I'm looking for remote, part-time work where my experience counts, "
              "and I want to contribute to how AI coding models get better.",
        "es": "Por dos razones. Primero, el trabajo en sí: {empresa} necesita ingenieros que tomen un cambio real y lo conviertan en una tarea justa y "
              "difícil, y ese es el tipo de análisis que he hecho por años. Segundo, el momento: busco un trabajo remoto de medio tiempo donde mi "
              "experiencia cuente, y quiero aportar a que los modelos de IA programen mejor."},
    # ---------------- Personales (STAR) ----------------
    "aprender": {
        "en": "Situation: {logro}. Task: I had to become productive fast, with little documentation. Action: I read the code end to end, drew a map of "
              "the main flows, and tested small changes before touching anything important. Result: within [about a month] I was fixing defects and "
              "training others. I use the same method today with new languages and tools.",
        "es": "Situación: {logro}. Tarea: tenía que ser productivo rápido y casi sin documentación. Acción: leí el código completo, hice un mapa de los "
              "flujos principales y probé cambios pequeños antes de tocar algo importante. Resultado: en [más o menos un mes] ya corregía errores y "
              "capacitaba a otros. Hoy aplico el mismo método con lenguajes y herramientas nuevas."},
    "problema": {
        "en": "Situation: {logro}. The hardest part was a bug that only appeared with real data. Action: I reproduced it with a copy of production data, "
              "wrote down hypotheses, and checked them one by one with logs and small tests until I found the root cause: [the real cause]. I fixed it "
              "and added a test so it couldn't come back. Result: [the measurable result, for example zero data loss].",
        "es": "Situación: {logro}. Lo más difícil fue un error que solo aparecía con datos reales. Acción: lo reproduje con una copia de los datos, "
              "anoté hipótesis y las comprobé una por una con registros y pruebas pequeñas hasta encontrar la causa: [la causa real]. Lo corregí y "
              "agregué una prueba para que no volviera. Resultado: [el resultado medible, por ejemplo cero pérdida de datos]."},
    "explicar": {
        "en": "In my consulting work I often explain technical changes to business owners. For example: {logro}. Instead of talking about tables "
              "and code, I explained it as before and after: what the user did before, what changes, and what risk it removes. I used one simple "
              "analogy and checked understanding by asking them to tell me the impact in their own words. Result: [they approved it the same day].",
        "es": "En mi consultoría explico a menudo cambios técnicos a dueños de negocio. Por ejemplo: {logro}. En vez de hablar de tablas y código, lo "
              "expliqué como un antes y un después: qué hacía el usuario antes, qué cambia y qué riesgo elimina. Usé una sola analogía y comprobé que me "
              "entendieran pidiéndoles que me dijeran el impacto con sus palabras. Resultado: [lo aprobaron el mismo día]."},
    "retro": {
        "en": "Situation: {logro}. A senior reviewer pointed out that my solution handled the normal case but not [an edge case]. I didn't defend it; I "
              "asked for an example, reproduced the problem and rewrote that part with tests for the edge cases. Result: the next version passed review, "
              "and since then I write the edge-case tests before I submit anything.",
        "es": "Situación: {logro}. Un revisor me señaló que mi solución cubría el caso normal pero no [un caso borde]. No me defendí: pedí un ejemplo, "
              "reproduje el problema y reescribí esa parte con pruebas para los casos borde. Resultado: la siguiente versión pasó la revisión y desde "
              "entonces escribo esas pruebas antes de entregar."},
    "conflicto": {
        "en": "A client wanted to [add a feature quickly by copying data between systems]; I thought it would create inconsistencies. I listened to "
              "why it mattered to them, then showed a small test with their own data that revealed the risk. We agreed on a simpler version that met "
              "their deadline without the risk. Result: it went live on time and the relationship got stronger.",
        "es": "Un cliente quería [agregar una función rápido copiando datos entre sistemas]; yo pensaba que crearía inconsistencias. Escuché por qué era "
              "importante para él y le mostré una prueba pequeña con sus propios datos que dejaba ver el riesgo. Acordamos una versión más simple que "
              "cumplía su plazo sin ese riesgo. Resultado: salió a tiempo y la relación se fortaleció."},
    "fallo": {
        "en": "On one project I underestimated [the data cleanup], and we missed the first delivery date. I told the client right away, split the work "
              "into smaller deliveries and added a daily check of the data. We delivered [two weeks] later with no errors. What I learned: I now "
              "estimate data work separately and validate a sample before committing to dates.",
        "es": "En un proyecto subestimé [la limpieza de datos] y no cumplimos la primera fecha. Le avisé al cliente de inmediato, dividí el trabajo en "
              "entregas más pequeñas y agregué una revisión diaria de los datos. Entregamos [dos semanas] después y sin errores. Lo que aprendí: ahora "
              "estimo el trabajo de datos por separado y valido una muestra antes de comprometer fechas."},
    "prioridades": {
        "en": "I've worked independently for years running my own firm. I block fixed hours on my calendar, keep a short checklist per task, and "
              "finish each work session by writing down the next step. Before I submit anything I run my own review: tests pass, the brief is clear, "
              "and I tried to break my own solution. If I'm blocked, I say so early with a concrete question.",
        "es": "Llevo años trabajando de forma independiente con mi propia firma. Bloqueo horas fijas en el calendario, llevo una lista corta por tarea y "
              "cierro cada sesión anotando el siguiente paso. Antes de entregar hago mi propia revisión: las pruebas pasan, el enunciado es claro y "
              "traté de romper mi propia solución. Si me bloqueo, lo digo temprano con una pregunta concreta."},
    "reglas": {
        "en": "Situation: {logro}. The rules were strict: [regulatory or client standards]. I turned the rules into a checklist, verified every item "
              "twice before delivery, and when something was ambiguous I asked instead of guessing and wrote the answer down for the team. Result: "
              "[zero rework or audit findings].",
        "es": "Situación: {logro}. Las reglas eran estrictas: [normas regulatorias o del cliente]. Convertí las reglas en una lista de chequeo, verifiqué "
              "cada punto dos veces antes de entregar y, cuando algo era ambiguo, pregunté en vez de suponer y dejé la respuesta escrita para el equipo. "
              "Resultado: [cero reprocesos o hallazgos de auditoría]."},
    "simple": {
        "en": "Imagine a lunchbox that already has everything your sandwich needs: bread, cheese, even the knife. Wherever you take it, at school or "
              "at a friend's house, you get exactly the same sandwich. A container is like that lunchbox for a program: it carries the program and "
              "everything it needs, so it works the same on any computer.",
        "es": "Imagina una lonchera que ya trae todo lo que tu sándwich necesita: pan, queso y hasta el cuchillo. La lleves al colegio o a casa de un "
              "amigo, siempre te queda el mismo sándwich. Un contenedor es esa lonchera para un programa: lleva el programa y todo lo que necesita, así "
              "funciona igual en cualquier computador."},
    # ---------------- Técnicas ----------------
    "estructuras": {
        "en": "I choose a hash map when I need fast lookup by a key: on average it's constant time, O(1), while searching a list is O(n). A tree, or a "
              "sorted structure, is better when I also need order or ranges, with O(log n) lookups. For example, when I migrated records between "
              "systems I loaded the old IDs into a dictionary to match each record in one step instead of scanning the whole list, which turned a "
              "job of hours into minutes.",
        "es": "Escojo un diccionario (hash map) cuando necesito buscar rápido por una clave: en promedio es tiempo constante, O(1), mientras que buscar "
              "en una lista es O(n). Un árbol o una estructura ordenada es mejor si también necesito orden o rangos, con búsquedas O(log n). Por "
              "ejemplo, al migrar registros cargué los identificadores viejos en un diccionario para emparejar cada registro en un paso en vez de "
              "recorrer la lista completa; un proceso de horas pasó a minutos."},
    "python": {
        "en": "I use a virtual environment per project, a src package with small modules, and pinned dependencies in requirements or pyproject. Tests "
              "go in pytest, with a fast unit suite and a few end-to-end tests. I run a formatter and a linter before each commit, use type hints in "
              "public functions, and keep configuration and secrets out of the code.",
        "es": "Uso un entorno virtual por proyecto, un paquete con módulos pequeños y dependencias con versión fija en requirements o pyproject. Las "
              "pruebas van en pytest, con pruebas unitarias rápidas y algunas de punta a punta. Paso un formateador y un linter antes de cada commit, "
              "uso type hints en las funciones públicas y dejo la configuración y las claves fuera del código."},
    "typescript": {
        "en": "TypeScript catches type errors at compile time and makes refactoring safer. But the types disappear at runtime: data from an API or a "
              "file can still be wrong, and 'any' turns checking off. So I validate external data at the boundary and prefer 'unknown' over 'any'.",
        "es": "TypeScript detecta errores de tipo al compilar y hace más seguros los cambios. Pero los tipos desaparecen al ejecutar: los datos de una "
              "API o un archivo pueden venir mal, y 'any' apaga la verificación. Por eso valido los datos externos en la entrada y prefiero 'unknown' a 'any'."},
    "go": {
        "en": "Go runs concurrent work in goroutines and coordinates them with channels. To avoid race conditions I don't share memory without "
              "protection: I pass data through channels or guard it with a sync.Mutex, use context for cancellation, and run tests with the -race flag.",
        "es": "Go ejecuta trabajo concurrente en goroutines y las coordina con channels. Para evitar condiciones de carrera no comparto memoria sin "
              "protección: paso datos por channels o los protejo con sync.Mutex, uso context para cancelar y corro las pruebas con -race."},
    "rust": {
        "en": "Every value in Rust has one owner, and when the owner goes out of scope the memory is freed. You can borrow a value many times read-only, "
              "or once mutably, never both. The compiler checks this, so you avoid use-after-free, double frees and data races without a garbage collector.",
        "es": "En Rust cada valor tiene un solo dueño, y cuando el dueño sale de alcance se libera la memoria. Se puede prestar un valor muchas veces en "
              "solo lectura, o una sola vez para modificarlo, nunca ambas. El compilador lo verifica, y así se evitan errores de memoria y data races."},
    "java": {
        "en": "I apply SOLID where it pays off: one responsibility per class, depend on interfaces at the boundaries such as database or external "
              "services, so I can test with fakes. I avoid creating interfaces with a single implementation 'just in case'. Simple code that's easy "
              "to test beats a perfect diagram.",
        "es": "Aplico SOLID donde rinde: una responsabilidad por clase y dependencia de interfaces en los bordes, como la base de datos o servicios "
              "externos, para poder probar con simulaciones. Evito crear interfaces con una sola implementación 'por si acaso'. Código simple y fácil de "
              "probar vale más que un diagrama perfecto."},
    "cpp": {
        "en": "In modern C++ I use RAII: resources are acquired in a constructor and released in the destructor. I use unique_ptr by default, "
              "shared_ptr only when ownership is really shared, and avoid manual new and delete.",
        "es": "En C++ moderno uso RAII: el recurso se toma en el constructor y se libera en el destructor. Uso unique_ptr por defecto, shared_ptr solo si "
              "la propiedad es realmente compartida, y evito new y delete manuales."},
    "docker": {
        "en": "I'd write a Dockerfile that starts from a pinned base image, installs the exact dependency versions, and checks out the repository at "
              "the commit right before the change, the parent commit. Then I build the image, run the test suite inside the container and confirm "
              "the expected tests fail before the fix and pass after it. Anyone who builds that image gets the same result.",
        "es": "Escribiría un Dockerfile que parta de una imagen base con versión fija, instale las dependencias exactas y haga checkout del repositorio en "
              "el commit justo antes del cambio, el commit padre. Luego construyo la imagen, corro las pruebas dentro del contenedor y confirmo que las "
              "pruebas esperadas fallan antes de la corrección y pasan después. Quien construya esa imagen obtiene el mismo resultado."},
    "linux": {
        "en": "First I find the process with ps or top and check CPU and memory. Then the logs, with journalctl or the app's log file. strace shows "
              "what system call it's stuck on, and lsof shows open files and sockets. I also check disk space with df and memory with free. Only "
              "after understanding the cause would I restart it.",
        "es": "Primero ubico el proceso con ps o top y reviso CPU y memoria. Luego los registros, con journalctl o el log de la aplicación. strace muestra "
              "en qué llamada al sistema está detenido y lsof los archivos y conexiones abiertas. También reviso el disco con df y la memoria con free. "
              "Solo después de entender la causa lo reiniciaría."},
    "git": {
        "en": "I'd use git bisect: mark a good commit and a bad one, and Git checks out the middle each time while I run the test, until it finds the "
              "exact commit. git log and git blame help confirm it. To see the code right before that change, I check out the parent commit with "
              "'git checkout <hash>^', usually on a new branch.",
        "es": "Usaría git bisect: marco un commit bueno y uno malo, y Git va probando el punto medio mientras corro la prueba, hasta encontrar el commit "
              "exacto. git log y git blame ayudan a confirmarlo. Para ver el código justo antes de ese cambio hago checkout del commit padre con "
              "'git checkout <hash>^', normalmente en una rama nueva."},
    "pruebas": {
        "en": "I test behavior, not my implementation: inputs and expected outputs, including edge cases and hidden cases the solver can't see. I add "
              "negative tests that a shortcut would fail, for example hard-coding the visible examples. Then I try to break my own checks with lazy "
              "and wrong solutions; if any of them passes, the checks aren't good enough yet.",
        "es": "Pruebo el comportamiento y no mi implementación: entradas y salidas esperadas, con casos borde y casos ocultos que quien resuelve no ve. "
              "Agrego pruebas negativas que un atajo no pasaría, por ejemplo escribir a mano los ejemplos visibles. Luego intento romper mis propias "
              "pruebas con soluciones flojas e incorrectas; si alguna pasa, las pruebas todavía no son suficientes."},
    "ia_codigo": {
        "en": "I use Claude and ChatGPT daily: I direct the design, ask for code in small pieces and review everything. A real example: [the model "
              "wrote a date calculation that ignored holidays]. It looked right, but my test with a real case failed, so I caught it before it "
              "reached the client. My rule: never accept generated code without a test that proves it.",
        "es": "Uso Claude y ChatGPT a diario: yo dirijo el diseño, pido el código por partes y reviso todo. Un ejemplo real: [el modelo escribió un "
              "cálculo de fechas que ignoraba los festivos]. Parecía correcto, pero mi prueba con un caso real falló y lo detecté antes de que llegara "
              "al cliente. Mi regla: nunca acepto código generado sin una prueba que lo demuestre."},
    "rubrica": {
        "en": "I'd start from a real change I understand deeply. The brief explains the goal clearly, without giving away the solution. The grading "
              "checks test behavior with hidden cases and edge cases, so shortcuts fail. Then I run the task against strong models: if they solve it "
              "easily, I make it require more real context from the codebase; if a skilled engineer can't solve it from the brief, I make the brief clearer.",
        "es": "Partiría de un cambio real que entiendo a fondo. El enunciado explica el objetivo con claridad, sin regalar la solución. Las verificaciones "
              "prueban el comportamiento con casos ocultos y casos borde para que los atajos fallen. Luego corro la tarea contra modelos fuertes: si la "
              "resuelven fácil, hago que exija más contexto real del código; si un ingeniero hábil no puede resolverla con el enunciado, lo aclaro."},
    "open_source": {
        "en": "In my own project, [name it], I changed [what]. The problem was [the bug or need]. I wrote a test that reproduced it, made the change, "
              "and confirmed the new test passed and the existing ones still passed. In my own words: before, [what happened]; after, [what happens "
              "now]. That's the kind of change I'd turn into a task.",
        "es": "En mi propio proyecto, [nombre], cambié [qué]. El problema era [el error o la necesidad]. Escribí una prueba que lo reproducía, hice el "
              "cambio y confirmé que la prueba nueva pasaba y que las existentes seguían pasando. En mis palabras: antes, [qué pasaba]; después, [qué "
              "pasa ahora]. Ese es el tipo de cambio que convertiría en una tarea."},
    "bases_datos": {
        "en": "I inventory and map both schemas field by field, run the migration first on a copy, and validate with record counts and checksums per "
              "table. I prepare a rollback plan and a short cutover window. That's how I worked in a real case: {logro}.",
        "es": "Hago el inventario y el mapeo de ambos esquemas campo por campo, corro la migración primero en una copia y valido con conteos y sumas de "
              "control por tabla. Preparo un plan de reversa y una ventana de corte corta. Así trabajé en un caso real: {logro}."},
    "distribuidos": {
        "en": "The hard part is partial failures: one service answers, another times out. I make operations idempotent so retries are safe, and I test "
              "retries and timeouts by simulating slow or failing dependencies with mocks or fault injection, using fixed seeds so tests are deterministic.",
        "es": "Lo difícil son las fallas parciales: un servicio responde y otro se demora. Hago las operaciones idempotentes para que reintentar sea seguro, "
              "y pruebo reintentos y tiempos de espera simulando dependencias lentas o caídas, con datos fijos para que las pruebas sean deterministas."},
    "seguridad": {
        "en": "I work only on my own encrypted computer, with a password manager and two-factor authentication. Secrets go in environment variables, "
              "never in the code or in Git. I don't publish client work anywhere, and I keep each client's files separated.",
        "es": "Trabajo solo en mi propio computador cifrado, con gestor de claves y verificación en dos pasos. Las claves van en variables de entorno, nunca "
              "en el código ni en Git. No publico trabajo de clientes en ningún lado y mantengo separados los archivos de cada cliente."},
    "apis": {
        "en": "{logro}. I agreed on a data contract first, validated every record at the entrance, logged the ones that didn't match instead of "
              "dropping them, and retried temporary failures. A daily reconciliation compared totals on both sides. Result: [zero lost records].",
        "es": "{logro}. Primero acordé un contrato de datos, validé cada registro a la entrada, registré los que no coincidían en vez de descartarlos y "
              "reintenté las fallas temporales. Una conciliación diaria comparaba los totales de ambos lados. Resultado: [cero registros perdidos]."},
    "agentes": {
        "en": "I haven't built a formal RL environment yet, so I'll be direct about that. My approach would be: a reproducible starting state, for "
              "example a container at a known commit; a clear goal; and an automatic score that checks the result, not the steps. I'd test it first "
              "with a correct and a wrong solution to make sure the score separates them.",
        "es": "Todavía no he construido un entorno formal de RL, y lo digo con franqueza. Mi enfoque sería: un estado inicial reproducible, por ejemplo un "
              "contenedor en un commit conocido; un objetivo claro, y un puntaje automático que verifique el resultado y no los pasos. Lo probaría "
              "primero con una solución correcta y una incorrecta para asegurar que el puntaje las distingue."},
    # ---------------- Cierre ----------------
    "disponibilidad": {
        "en": "I can commit {horas} starting [this week]. I usually work [mornings, Eastern time], and I can adjust to review deadlines.",
        "es": "Puedo dedicar {horas} desde [esta semana]. Normalmente trabajo [en las mañanas, hora del Este] y me adapto a los plazos de revisión."},
    "preguntas": {
        "en": "Yes, thank you. What separates work that passes review on the first round from work that needs several? And what are the next steps after this interview?",
        "es": "Sí, gracias. ¿Qué distingue un trabajo que se aprueba en la primera revisión de uno que necesita varias? ¿Y cuáles son los siguientes pasos?"},
}

GENERICOS = {
    "cv": {"en": "Sure. {logro}. The situation was [context]. My role was [your exact role]. I [the two or three things you did]. "
                 "As a result, [the measurable result].",
           "es": "Claro. {logro}. El contexto era [contexto]. Mi papel fue [su papel exacto]. Yo [las dos o tres cosas que hizo]. "
                 "Como resultado, [el resultado medible]."},
    "caso": {"en": "I'd do it in steps. First, [understand the starting point and pick a real example]. Second, [do the core work], keeping notes "
                   "of each decision. Third, I'd verify it: run the tests, try wrong and shortcut versions to make sure the checks catch them, "
                   "and compare against the expected result. Finally, I'd review it with fresh eyes before submitting.",
             "es": "Lo haría por pasos. Primero, [entender el punto de partida y escoger un ejemplo real]. Segundo, [hacer el trabajo central], "
                   "anotando cada decisión. Tercero, lo verificaría: correr las pruebas, intentar versiones incorrectas y atajos para asegurar que las "
                   "verificaciones los atrapan, y comparar con el resultado esperado. Por último, lo revisaría con calma antes de entregar."},
    "brecha": {"en": "To be honest, I haven't done exactly that yet. The closest is: {logro}. To close the gap, I'm [taking a course or building a "
                     "small project] and I expect to have [a concrete result] by [date].",
               "es": "Para ser honesto, todavía no he hecho exactamente eso. Lo más cercano es: {logro}. Para cerrar esa brecha estoy [haciendo un "
                     "curso o un proyecto pequeño] y espero tener [un resultado concreto] para [fecha]."},
    "simple": {"en": "Imagine [an everyday object the child knows]. [Concept] works the same way: [one sentence linking the two]. "
                     "That's why it's useful: [one benefit in plain words].",
               "es": "Imagina [un objeto cotidiano que el niño conozca]. [El concepto] funciona igual: [una frase que los conecte]. "
                     "Por eso sirve: [un beneficio en palabras simples]."},
    "libre": {"en": "[Give a direct answer in one sentence.] For example: {logro}. [Close with why it matters for this role.]",
              "es": "[Responda directo en una frase.] Por ejemplo: {logro}. [Cierre con por qué importa para esta posición.]"},
}


def primera_persona(frase, lengua="en"):
    """'Led the migration…' → 'I led the migration…' (las hojas de vida omiten el sujeto)."""
    frase = frase.strip().rstrip(".")
    if lengua != "en" or not frase:
        return frase
    primera, _, resto = frase.partition(" ")
    if primera in ("I", "My", "We"):
        return frase
    if primera.endswith("ed") or primera in ("Built", "Led", "Ran", "Wrote", "Made", "Set", "Built,"):
        return f"I {primera.lower()} {resto}"
    if re.fullmatch(r"[A-Z][a-z]+s", primera):
        return f"I {primera[:-1].lower()} {resto}"
    return frase


def ejemplo(pregunta, lengua, hoja=None, datos=None):
    """Una respuesta de ejemplo en el idioma de la entrevista, con datos reales de la hoja de vida cuando los hay."""
    datos = dict(datos or {})
    lengua = "es" if lengua == "es" else "en"
    apoyo = [a for a in pregunta.get("apoyo", []) if not a.endswith("?")]
    lineas = [l.strip() for l in (hoja or {}).get("texto", "").splitlines() if l.strip()]
    titular = next((l for l in lineas[:6] if re.search(r"engineer|manager|developer|ingenier|gerente", l, re.I)), "")
    perfil = next((l for l in lineas if len(l) > 150), "")
    perfil = re.split(r"(?<=\.)\s", perfil)[0] if perfil else ""
    logro_base = next((a for a in apoyo if a not in (titular, perfil) and len(a) > 40), "")
    if not logro_base:
        logro_base = next((l for l in lineas if re.match(r"(Led|Reverse|Built|Developed|Founded)", l)), "")
    datos.setdefault("logro", primera_persona(logro_base, lengua) if logro_base else
                     ("[a concrete example from your experience]" if lengua == "en" else "[un ejemplo concreto de su experiencia]"))
    datos.setdefault("titular", titular.rstrip(".") or ("[your current title]" if lengua == "en" else "[su cargo actual]"))
    datos.setdefault("perfil", perfil)
    datos.setdefault("puesto", "")
    datos.setdefault("empresa", "the company" if lengua == "en" else "la empresa")
    datos.setdefault("horas", "the hours you need" if lengua == "en" else "las horas que necesitan")
    pid = pregunta.get("id", "")
    base = MODELOS.get(pid)
    if pid == "simple" and not re.search(r"docker|contenedor|container", pregunta.get("texto", ""), re.I):
        base = GENERICOS["simple"]
    if not base:
        clave = ("cv" if pid.startswith("cv_") else "caso" if pid.startswith("caso_") else
                 "brecha" if pid.startswith("brecha_") else "libre")
        base = GENERICOS[clave]
    texto = base[lengua]
    for k, v in datos.items():
        texto = texto.replace("{" + k + "}", str(v))
    return re.sub(r"\s{2,}", " ", texto).strip()
