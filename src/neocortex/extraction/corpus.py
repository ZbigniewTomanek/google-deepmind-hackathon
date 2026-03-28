"""Medical domain seed corpus for NeoCortex PoC demo.

Three passages covering neurology, pharmacy, and sexual function with
cross-domain connections (SSRIs bridge pharmacy ↔ sexual function,
serotonin bridges neurology ↔ pharmacy).
"""

from __future__ import annotations

MEDICAL_SEED_MESSAGES: list[dict] = [
    {
        "id": "med-001",
        "title": "Serotonin and Mood Regulation",
        "topic": "neurology",
        "content": (
            "Serotonin (5-hydroxytryptamine, 5-HT) is a monoamine neurotransmitter "
            "primarily found in the gastrointestinal tract, blood platelets, and the "
            "central nervous system. In the brain, serotonin is synthesized in the "
            "raphe nuclei of the brainstem from the amino acid tryptophan via "
            "tryptophan hydroxylase. Serotonergic projections from the dorsal and "
            "median raphe nuclei innervate widespread cortical and subcortical regions. "
            "Serotonin modulates mood, appetite, sleep, and cognitive functions "
            "including memory and learning. At least 14 serotonin receptor subtypes "
            "have been identified, with 5-HT1A and 5-HT2A playing central roles in "
            "mood regulation. Dysregulation of serotonin signaling is implicated in "
            "major depressive disorder, anxiety disorders, and obsessive-compulsive "
            "disorder. The serotonin transporter (SERT) is the primary mechanism for "
            "reuptake of serotonin from the synaptic cleft back into the presynaptic "
            "neuron, making it a key pharmacological target."
        ),
    },
    {
        "id": "med-002",
        "title": "SSRIs: Mechanism and Clinical Use",
        "topic": "pharmacy",
        "content": (
            "Selective serotonin reuptake inhibitors (SSRIs) are the most widely "
            "prescribed class of antidepressants worldwide. They work by selectively "
            "blocking the serotonin transporter (SERT), preventing reuptake of "
            "serotonin from the synaptic cleft and increasing its availability for "
            "postsynaptic receptors. Common SSRIs include fluoxetine (Prozac), "
            "sertraline (Zoloft), paroxetine (Paxil), citalopram (Celexa), and "
            "escitalopram (Lexapro). SSRIs are first-line treatment for major "
            "depressive disorder, generalized anxiety disorder, panic disorder, "
            "social anxiety disorder, and obsessive-compulsive disorder. Therapeutic "
            "effects typically take 2-4 weeks to manifest due to downstream "
            "neuroplastic changes including 5-HT1A autoreceptor desensitization. "
            "Side effects include nausea, insomnia, weight changes, and sexual "
            "dysfunction. SSRIs have a favorable safety profile compared to older "
            "tricyclic antidepressants and monoamine oxidase inhibitors."
        ),
    },
    {
        "id": "med-003",
        "title": "SSRI-Induced Sexual Dysfunction",
        "topic": "sexual function",
        "content": (
            "SSRI-induced sexual dysfunction is one of the most common adverse effects "
            "of serotonergic antidepressants, affecting 30-70% of patients. Symptoms "
            "include decreased libido, erectile dysfunction in males, reduced vaginal "
            "lubrication in females, delayed ejaculation, and anorgasmia. The mechanism "
            "involves serotonin's inhibitory effect on dopaminergic and noradrenergic "
            "pathways that mediate sexual arousal and orgasm. Specifically, increased "
            "serotonin at 5-HT2A and 5-HT2C receptors suppresses dopamine release in "
            "the mesolimbic pathway, while stimulation of spinal 5-HT2A receptors "
            "inhibits the ejaculatory reflex. Management strategies include dose "
            "reduction, drug holidays (not recommended for paroxetine due to "
            "discontinuation syndrome), switching to bupropion or mirtazapine, or "
            "augmentation with phosphodiesterase-5 inhibitors such as sildenafil. "
            "Post-SSRI sexual dysfunction (PSSD) is a rare but recognized condition "
            "where sexual symptoms persist after SSRI discontinuation."
        ),
    },
]
