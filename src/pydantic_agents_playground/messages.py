from pydantic_agents_playground.schemas import SeedMessage

SEED_MESSAGES: list[SeedMessage] = [
    SeedMessage(
        message_id="msg-001",
        title="E21 sets the template",
        topic="history",
        content=(
            "The first BMW 3 Series arrived as the E21 in the 1970s and helped define the compact executive "
            "formula. It was sold as a smaller, driver-focused sedan positioned below the 5 Series."
        ),
    ),
    SeedMessage(
        message_id="msg-002",
        title="E30 M3 homologation icon",
        topic="motorsport",
        content=(
            "BMW developed the E30 M3 as a homologation special for touring car racing. The car became famous "
            "for DTM and other touring car success, linking the 3 Series closely with motorsport."
        ),
    ),
    SeedMessage(
        message_id="msg-003",
        title="Inline-six reputation in the E36 and E46 years",
        topic="powertrain",
        content=(
            "During the E36 and E46 era, smooth inline-six engines were a defining part of many BMW 3 Series "
            "models. Enthusiasts often point to the balance and sound of those six-cylinder cars."
        ),
    ),
    SeedMessage(
        message_id="msg-004",
        title="E46 M3 CSL remains an enthusiast reference point",
        topic="performance",
        content=(
            "The BMW E46 M3 CSL is widely remembered as a lighter, sharper version of the standard E46 M3. "
            "It emphasized track-oriented performance, reduced weight, and a more focused driving character."
        ),
    ),
    SeedMessage(
        message_id="msg-005",
        title="320d becomes a European staple",
        topic="diesel",
        content=(
            "For many European buyers, the BMW 320d became one of the most important 3 Series variants. Its "
            "diesel engine blended strong fuel economy with enough torque for everyday motorway use."
        ),
    ),
    SeedMessage(
        message_id="msg-006",
        title="335i and the N54 tuning era",
        topic="turbocharging",
        content=(
            "The turbocharged BMW 335i introduced many drivers to the tuning potential of the N54 engine family. "
            "That model gained a reputation for strong straight-line performance and easy aftermarket power gains."
        ),
    ),
    SeedMessage(
        message_id="msg-007",
        title="Touring keeps the wagon in the lineup",
        topic="body_style",
        content=(
            "BMW has long offered Touring versions of the 3 Series for buyers who wanted wagon practicality. "
            "The Touring body style kept the car useful for families while preserving the brand's sporty image."
        ),
    ),
    SeedMessage(
        message_id="msg-008",
        title="xDrive broadens the 3 Series brief",
        topic="drivetrain",
        content=(
            "Later BMW 3 Series generations offered xDrive all-wheel drive on more models. That drivetrain made "
            "the car more appealing in cold climates and widened its everyday usability."
        ),
    ),
    SeedMessage(
        message_id="msg-009",
        title="330e adds plug-in hybrid capability",
        topic="hybrid",
        content=(
            "The BMW 330e brought a plug-in hybrid powertrain to the 3 Series range. It combined a gasoline "
            "engine, an electric motor, and a battery so the car could cover short trips with electric assistance."
        ),
    ),
    SeedMessage(
        message_id="msg-010",
        title="G20 and the M340i performance tier",
        topic="current_generation",
        content=(
            "In the G20 generation, the BMW M340i sits near the top of the regular 3 Series range without "
            "becoming a full M3. It is positioned as a fast, premium performance sedan with a turbocharged "
            "inline-six engine and modern driver-assistance technology."
        ),
    ),
]
