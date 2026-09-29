"""Public service pages (/servicios/<slug>). One entry per service; the template is
templates/servicios/servicio.html. Titles <= 60 and descriptions <= 155 characters
(tests/test_public_pages.py checks them). Facts only from what TOMATO already publishes:
no prices, zones or guarantees that aren't on the site."""

IMG = "/static/images"

SERVICIOS = {
    "reforestacion-para-empresas": {
        "nav": "Reforestación",
        "title": "Reforestación para empresas e instituciones | TOMATO",
        "description": "Reforestación en Costa Rica con ingenieros forestales, vivero propio y GPS por árbol en "
                       "un mapa público. Para empresas, municipalidades y metas ESG.",
        "h1": "Reforestación para empresas e instituciones",
        "kicker": "Especialidad insignia",
        "lead": "Planes de reforestación dirigidos por ingenieros forestales, con plantas de nuestro vivero y la "
                "coordenada GPS de cada árbol en un mapa público. Una reforestación que tu empresa o institución "
                "puede medir, comprobar y mostrar.",
        "motor": "esg",
        "service_type": "Reforestación",
        "hero": (f"{IMG}/servicios/reforestacion.jpg", 600, 800,
                 "Dos personas del equipo de TOMATO abriendo con un barreno el hoyo para sembrar un árbol en un parque",
                 "center 20%"),
        "for_whom": [
            ("Empresas con metas ESG", "Reforestación con datos verificables para informes de sostenibilidad y "
                                       "juntas directivas."),
            ("Municipalidades e instituciones", "Recuperación de zonas verdes y áreas públicas, con cada árbol "
                                                "georreferenciado."),
            ("Voluntariado corporativo", "Jornadas de siembra con tu equipo a través del programa Dárboles."),
        ],
        "intro": [
            "Basados en nuestra experiencia en proyectos de reforestación, ejecutamos planes integrales orientados "
            "a la recuperación ecológica y la compensación ambiental. Contamos con nuestro propio vivero para "
            "garantizar la calidad y la adaptabilidad de cada individuo, con el seguimiento de nuestro servicio de "
            "ingenieros forestales.",
            "Nos diferenciamos por aplicar tecnología y ciencia en el campo: cada árbol plantado tiene control "
            "individual por coordenadas GPS, y usamos hidrokeeper, un polímero retenedor de agua, para ayudar a "
            "la planta a sobrevivir la época seca.",
        ],
        "includes": [
            "Provisión de individuos desde nuestro vivero, con genética adaptada.",
            "Dirección y ejecución de la siembra por ingenieros forestales.",
            "Control georreferenciado (coordenadas GPS) de cada individuo en el área.",
            "Aplicación de hidrokeeper para maximizar la supervivencia ante el estrés hídrico.",
            "Reportes periódicos y trazabilidad real de los resultados del proyecto.",
        ],
        "steps": [
            ("Diagnóstico del sitio", "Visitamos el área y definimos el alcance del proyecto."),
            ("Selección de especies", "Elegimos las plantas del vivero según el sitio."),
            ("Siembra con GPS", "Cada árbol queda registrado con su especie, sector y coordenada."),
            ("Monitoreo y reporte", "Actualizamos el estado de cada árbol y medimos la supervivencia."),
        ],
        "result": "Una reforestación exitosa, medible y con impacto ecológico comprobable a lo largo del tiempo.",
        "live_stats": True,
        "gallery": [
            (f"{IMG}/hero/siembra-960.jpg", 960, 1280, "Persona del equipo de TOMATO sembrando un árbol", "Siembra"),
            (f"{IMG}/proyectos/alajuela-parque.jpg", 768, 1024,
             "Persona del equipo de TOMATO sembrando junto al rótulo Área arborizada en un parque de Alajuela",
             "Municipalidad de Alajuela"),
            (f"{IMG}/proyectos/vivero.jpg", 768, 1024,
             "Hileras de bolsas con tierra listas para sembrar en el vivero", "Vivero propio"),
        ],
        "faq": [
            ("¿Cómo sé que los árboles siguen vivos?",
             "Después de la siembra hacemos monitoreos y actualizamos el estado de cada árbol: vivo, muerto, "
             "reemplazado o sin verificar. La supervivencia a 12 meses se calcula sobre los árboles verificados y "
             "se ve en el mapa público de reforestación."),
            ("¿Qué es el hidrokeeper?",
             "Es un polímero retenedor de agua que se aplica al sembrar. Guarda humedad cerca de la raíz y ayuda "
             "a la planta a resistir el estrés hídrico de la época seca."),
            ("¿De dónde salen las plantas?",
             "De nuestro propio vivero, con genética adaptada al sitio. Así controlamos la calidad de cada "
             "individuo antes de sembrarlo."),
            ("¿Puedo mostrar el proyecto en mis informes ESG?",
             "Sí. Entregamos reportes periódicos y cada árbol aparece en el mapa público con su coordenada. El "
             "nombre de tu empresa o institución se muestra solo si lo autorizás."),
            ("¿Cómo se cotiza un proyecto?",
             "Contanos el área, la ubicación y el objetivo del proyecto por el formulario o por WhatsApp. Te "
             "respondemos en menos de 24 horas y coordinamos una visita."),
        ],
    },
    "mantenimiento-de-zonas-verdes": {
        "nav": "Mantenimiento",
        "title": "Mantenimiento de zonas verdes en Costa Rica | TOMATO",
        "description": "Mantenimiento de zonas verdes para condominios, empresas y centros educativos: corte, "
                       "bordeado, control de maleza y limpieza. Cotizá en 24 horas.",
        "h1": "Mantenimiento de zonas verdes",
        "kicker": "Control, orden y presentación todo el año",
        "lead": "Rutinas de mantenimiento para que las áreas verdes se mantengan estables, limpias y con un acabado "
                "consistente, con la frecuencia que tu propiedad necesita.",
        "motor": "mantenimiento",
        "service_type": "Mantenimiento de zonas verdes",
        "hero": (f"{IMG}/servicios/mantenimiento.jpg", 800, 600,
                 "Franja de césped recién cortado con bordes definidos y maceteros junto a un parqueo", "center 60%"),
        "for_whom": [
            ("Condominios y áreas comunes", "Zonas verdes presentables para quienes viven y visitan."),
            ("Empresas y centros educativos", "Buena presentación sin interrumpir la operación."),
            ("Propiedades residenciales", "Césped y bordes al día sin tener que estar pendiente."),
        ],
        "intro": [
            "Diseñamos y ejecutamos rutinas de mantenimiento para que las áreas verdes se mantengan estables, "
            "limpias y con un acabado consistente. Es ideal para condominios, empresas, centros educativos, áreas "
            "comunes y propiedades residenciales que requieren buena presentación sin interrupciones.",
            "El alcance se define por la frecuencia (semanal, quincenal, mensual o por demanda) y por la condición "
            "del sitio. Nos enfocamos en controlar el crecimiento, reducir la maleza, mantener los bordes definidos "
            "y dejar el área limpia y lista para usar al terminar.",
        ],
        "includes": [
            "Corte de césped a la altura adecuada según la temporada y el tipo de área.",
            "Bordeado de aceras, jardineras, árboles y límites de zona verde.",
            "Control de maleza y limpieza general del área intervenida.",
            "Recolección y disposición de residuos vegetales según las condiciones del sitio.",
            "Recomendaciones de frecuencia para evitar deterioro y costos correctivos.",
        ],
        "steps": [
            ("Visita y diagnóstico", "Alcance, frecuencia y puntos críticos del sitio."),
            ("Plan de trabajo", "Tareas, periodicidad y estándares de acabado."),
            ("Ejecución", "Operación ordenada y supervisada en sitio."),
            ("Seguimiento", "Continuidad, ajustes y mejora progresiva."),
        ],
        "result": "Áreas verdes uniformes, limpias y con un estándar visible de orden y mantenimiento.",
        "gallery": [
            (f"{IMG}/proyectos/mantenimiento-residencial.jpg", 1040, 780,
             "Jardín residencial con césped recién cortado y bordes definidos", "Residencial"),
            (f"{IMG}/proyectos/museo-jardin.jpg", 1040, 780,
             "Jardín de esculturas del Museo de Arte Costarricense con setos, flores y senderos",
             "Museo de Arte Costarricense"),
        ],
        "faq": [
            ("¿Con qué frecuencia se hace el mantenimiento?",
             "Semanal, quincenal, mensual o por demanda. La recomendamos después de la visita, según el tipo de "
             "área, el crecimiento y el uso del sitio."),
            ("¿Se llevan los residuos vegetales?",
             "Sí: la recolección y disposición de los residuos es parte del servicio, según las condiciones del "
             "sitio."),
            ("¿Cómo se define el precio?",
             "Por el área, la frecuencia y la condición del sitio. Por eso cotizamos después de una visita, sin "
             "compromiso."),
            ("¿Atienden condominios y empresas?",
             "Sí. Trabajamos con condominios, empresas, centros educativos, áreas comunes y propiedades "
             "residenciales."),
            ("¿Cómo pido una cotización?",
             "Por el formulario o por WhatsApp, con la ubicación, el área aproximada y la frecuencia que buscás. "
             "Te respondemos en menos de 24 horas."),
        ],
    },
    "jardineria": {
        "nav": "Jardinería",
        "title": "Jardinería profesional en Costa Rica | TOMATO",
        "description": "Jardinería para entradas, jardines frontales y áreas de alto tránsito: podas, limpieza de "
                       "camas, fertilización y reposición de plantas. Cotizá en 24 horas.",
        "h1": "Jardinería profesional",
        "kicker": "Detalle, salud de plantas y estética controlada",
        "lead": "La jardinería es donde se define el acabado de la propiedad: plantas, arbustos y camas en "
                "condiciones óptimas, con una estética cuidada y coherente.",
        "motor": "mantenimiento",
        "service_type": "Jardinería",
        "hero": (f"{IMG}/servicios/jardineria.jpg", 800, 600,
                 "Cama de jardín con bromelias, un arbusto de flores moradas y césped bordeado junto a setos",
                 "center 50%"),
        "for_whom": [
            ("Entradas y jardines frontales", "La primera impresión de la propiedad."),
            ("Áreas de alto tránsito", "Espacios que se ven todos los días y necesitan orden."),
            ("Empresas y residencias", "Jardines con continuidad visual, sin vacíos."),
        ],
        "intro": [
            "Nos enfocamos en mantener plantas, arbustos y elementos decorativos en condiciones óptimas, con una "
            "estética cuidada y coherente. Es ideal para entradas, jardines frontales, áreas de alto tránsito y "
            "espacios que requieren buena impresión.",
            "Trabajamos con podas de formación, control de crecimiento y limpieza de camas. Cuando aplica, "
            "incorporamos ajustes de suelo, fertilización según necesidad y reposición de plantas para mantener "
            "la continuidad visual. El objetivo es evitar jardines cansados, desordenados o con vacíos.",
        ],
        "includes": [
            "Poda de arbustos y plantas ornamentales para forma y control.",
            "Limpieza de camas y jardineras: hojas secas, maleza y residuos.",
            "Reposición de plantas, según diseño y disponibilidad, para mantener la estética.",
            "Fertilización y mejoras puntuales según el diagnóstico del sitio.",
            "Detalle final: alineación visual, limpieza de bordes y presentación.",
        ],
        "steps": [
            ("Visita y diagnóstico", "Estado de plantas, camas y suelo."),
            ("Plan de trabajo", "Podas, reposiciones y frecuencia."),
            ("Ejecución", "Trabajo ordenado y supervisado en sitio."),
            ("Seguimiento", "Ajustes según cómo evoluciona el jardín."),
        ],
        "result": "Jardines con orden, salud y una presentación consistente.",
        "gallery": [
            (f"{IMG}/proyectos/museo-jardin.jpg", 1040, 780,
             "Jardín de esculturas del Museo de Arte Costarricense con setos, flores y senderos",
             "Museo de Arte Costarricense"),
            (f"{IMG}/servicios/paisajismo.jpg", 800, 600,
             "Jardín de esculturas con setos, flores y senderos de piedra roja en el Museo de Arte Costarricense",
             "Camas y senderos"),
        ],
        "faq": [
            ("¿Qué diferencia hay entre jardinería y mantenimiento de zonas verdes?",
             "El mantenimiento se ocupa del césped y de las áreas amplias con una rutina fija. La jardinería cuida "
             "las plantas, los arbustos y las camas: podas, reposiciones y el acabado de la propiedad."),
            ("¿Reponen las plantas que se pierden?",
             "Sí, según el diseño del jardín y la disponibilidad, para mantener la continuidad visual."),
            ("¿Fertilizan las plantas?",
             "Cuando el diagnóstico del sitio lo indica, con ajustes de suelo y fertilización según necesidad."),
            ("¿Cómo pido una cotización?",
             "Por el formulario o por WhatsApp, con la ubicación y lo que querés mejorar del jardín. Te "
             "respondemos en menos de 24 horas."),
        ],
    },
    "paisajismo": {
        "nav": "Paisajismo",
        "title": "Paisajismo y diseño de jardines en Costa Rica | TOMATO",
        "description": "Diseño e instalación de jardines pensados para durar: selección de especies, preparación "
                       "del área y plan de continuidad. Cotizá en 24 horas.",
        "h1": "Paisajismo y diseño de jardines",
        "kicker": "Diseño e instalación con visión de mantenimiento",
        "lead": "El paisajismo no es solo poner plantas: es crear un espacio funcional y estético que se pueda "
                "mantener en el tiempo.",
        "motor": "mantenimiento",
        "service_type": "Paisajismo",
        "hero": (f"{IMG}/servicios/paisajismo.jpg", 800, 600,
                 "Jardín de esculturas con setos, flores y senderos de piedra roja en el Museo de Arte Costarricense",
                 "center 55%"),
        "for_whom": [
            ("Proyectos corporativos", "Espacios que ordenan el entorno y elevan la presentación."),
            ("Residencias", "Jardines armónicos y fáciles de mantener."),
            ("Áreas por renovar", "Zonas que necesitan un diseño nuevo, no solo mantenimiento."),
        ],
        "intro": [
            "Diseñamos e instalamos soluciones que ordenan visualmente el entorno, mejoran el uso del espacio y "
            "elevan la presentación de la propiedad.",
            "Priorizamos criterios prácticos: la selección de especies, una distribución que evite el "
            "mantenimiento excesivo y una propuesta que considere riego, crecimiento y exposición. El resultado es "
            "un espacio más limpio, armónico y coherente con el entorno y con tu objetivo, corporativo o "
            "residencial.",
        ],
        "includes": [
            "Propuesta de diseño, según el alcance: distribución, estilo y criterios de mantenimiento.",
            "Selección e instalación de plantas y elementos verdes según el entorno.",
            "Preparación del área: limpieza, conformación y orden base para la instalación.",
            "Plan de continuidad: recomendaciones y rutina para mantener el resultado.",
            "Ajustes posteriores: reposiciones o correcciones puntuales según la evolución.",
        ],
        "steps": [
            ("Visita y diagnóstico", "Uso del espacio, riego, exposición y objetivo."),
            ("Propuesta", "Distribución, especies y criterios de mantenimiento."),
            ("Instalación", "Preparación del área e instalación de plantas."),
            ("Continuidad", "Rutina y ajustes para mantener el resultado."),
        ],
        "result": "Un espacio más armónico, ordenado y sostenible de mantener.",
        "gallery": [
            (f"{IMG}/proyectos/museo-jardin.jpg", 1040, 780,
             "Jardín de esculturas del Museo de Arte Costarricense con setos, flores y senderos",
             "Museo de Arte Costarricense"),
        ],
        "faq": [
            ("¿El servicio incluye el diseño?",
             "Sí: armamos una propuesta de diseño según el alcance, con la distribución, el estilo y los criterios "
             "de mantenimiento."),
            ("¿Cómo eligen las especies?",
             "Según el entorno, el riego disponible, el crecimiento y la exposición al sol, para que el jardín no "
             "exija un mantenimiento excesivo."),
            ("¿Pueden mantener el jardín después de instalarlo?",
             "Sí. Dejamos un plan de continuidad y podemos encargarnos de la jardinería y el mantenimiento de las "
             "zonas verdes."),
            ("¿Cómo pido una cotización?",
             "Por el formulario o por WhatsApp, con la ubicación, el área y la idea que tenés. Te respondemos en "
             "menos de 24 horas y coordinamos una visita."),
        ],
    },
}
