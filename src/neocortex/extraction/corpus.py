"""Medical domain seed corpus for NeoCortex PoC demo.

Ten passages covering neurology, pharmacy, and sexual function with
cross-domain connections (e.g. SSRIs bridge pharmacy ↔ sexual function,
dopamine bridges neurology ↔ pharmacy).
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
    {
        "id": "med-004",
        "title": "Dopamine Pathways and Reward",
        "topic": "neurology",
        "content": (
            "Dopamine is a catecholamine neurotransmitter synthesized from tyrosine "
            "via tyrosine hydroxylase and DOPA decarboxylase. Four major dopaminergic "
            "pathways exist in the brain: the mesolimbic pathway (ventral tegmental "
            "area to nucleus accumbens), involved in reward and motivation; the "
            "mesocortical pathway (VTA to prefrontal cortex), mediating executive "
            "function and working memory; the nigrostriatal pathway (substantia nigra "
            "to dorsal striatum), controlling voluntary movement; and the "
            "tuberoinfundibular pathway (hypothalamus to pituitary), regulating "
            "prolactin secretion. Dopamine acts through D1-like (D1, D5) and D2-like "
            "(D2, D3, D4) receptor families. The mesolimbic pathway is central to "
            "the brain's reward circuitry and is implicated in addiction, "
            "schizophrenia, and ADHD. Dopamine also plays a crucial role in sexual "
            "motivation and arousal, acting as a pro-sexual neurotransmitter in "
            "contrast to serotonin's generally inhibitory role."
        ),
    },
    {
        "id": "med-005",
        "title": "PDE5 Inhibitors in Erectile Dysfunction",
        "topic": "pharmacy / sexual function",
        "content": (
            "Phosphodiesterase type 5 (PDE5) inhibitors are the first-line "
            "pharmacological treatment for erectile dysfunction (ED). They work by "
            "inhibiting the enzyme PDE5, which breaks down cyclic guanosine "
            "monophosphate (cGMP) in the smooth muscle of the corpus cavernosum. "
            "During sexual stimulation, nitric oxide (NO) released from endothelial "
            "cells and nerve terminals activates guanylate cyclase, producing cGMP, "
            "which causes smooth muscle relaxation and penile erection. PDE5 "
            "inhibitors prolong this process. Sildenafil (Viagra), tadalafil "
            "(Cialis), and vardenafil (Levitra) are the major drugs in this class. "
            "Tadalafil has a longer half-life (17.5 hours) allowing daily dosing. "
            "These drugs are also used to treat pulmonary arterial hypertension "
            "(sildenafil as Revatio) and benign prostatic hyperplasia (tadalafil). "
            "PDE5 inhibitors are contraindicated with nitrates due to risk of "
            "severe hypotension. They can augment sexual function in patients with "
            "SSRI-induced erectile dysfunction."
        ),
    },
    {
        "id": "med-006",
        "title": "Neuroanatomy of Sexual Response",
        "topic": "neurology / sexual function",
        "content": (
            "The human sexual response involves a coordinated interplay between the "
            "central and peripheral nervous systems. The medial preoptic area (MPOA) "
            "of the hypothalamus serves as a key integrating center for sexual "
            "behavior, receiving inputs from the amygdala, bed nucleus of the stria "
            "terminalis, and olfactory system. The paraventricular nucleus (PVN) of "
            "the hypothalamus sends oxytocinergic projections to spinal autonomic "
            "centers controlling erection and ejaculation. Erection is primarily a "
            "parasympathetic function mediated by the pelvic splanchnic nerves (S2-S4), "
            "while ejaculation involves coordinated sympathetic (T10-L2) and somatic "
            "(pudendal nerve, S2-S4) activity. The spinal ejaculatory generator, "
            "located in the lumbar spinothalamic cells, coordinates the emission and "
            "expulsion phases. Descending serotonergic pathways from the raphe nuclei "
            "exert tonic inhibition on spinal sexual reflexes, explaining why elevated "
            "serotonin levels from SSRIs delay ejaculation and impair orgasm."
        ),
    },
    {
        "id": "med-007",
        "title": "Antiepileptic Drugs and Hormonal Effects",
        "topic": "pharmacy / sexual function",
        "content": (
            "Antiepileptic drugs (AEDs) can significantly affect sexual function "
            "through multiple mechanisms. Enzyme-inducing AEDs such as carbamazepine, "
            "phenytoin, and phenobarbital increase hepatic synthesis of sex "
            "hormone-binding globulin (SHBG), reducing bioavailable testosterone and "
            "estradiol. Valproate, a non-enzyme-inducing AED, is associated with "
            "polycystic ovary syndrome (PCOS), weight gain, and hyperandrogenism in "
            "women. Sexual dysfunction is reported in 30-60% of epilepsy patients on "
            "AED therapy, including reduced libido, erectile dysfunction, and "
            "menstrual irregularities. Newer AEDs such as lamotrigine and "
            "levetiracetam appear to have fewer endocrine side effects. "
            "Additionally, epileptic seizures themselves can originate from or "
            "propagate through temporal lobe and hypothalamic structures involved in "
            "sexual function, contributing to ictal and interictal sexual dysfunction. "
            "Gabapentin, while primarily an AED, is increasingly prescribed for "
            "neuropathic pain and has variable effects on sexual function."
        ),
    },
    {
        "id": "med-008",
        "title": "Multiple Sclerosis and Sexual Dysfunction",
        "topic": "neurology / sexual function",
        "content": (
            "Multiple sclerosis (MS) is an autoimmune demyelinating disease of the "
            "central nervous system that frequently causes sexual dysfunction, "
            "affecting 50-90% of men and 40-80% of women with MS. Primary sexual "
            "dysfunction results from demyelination of spinal cord pathways "
            "controlling genital sensation, erection, lubrication, and orgasm. "
            "Lesions in the cervical and thoracic spinal cord disrupt descending "
            "autonomic pathways, while sacral lesions impair the local reflex arcs "
            "for erection and vaginal engorgement. Secondary sexual dysfunction "
            "arises from MS symptoms such as fatigue, spasticity, bladder "
            "dysfunction, and pain. Tertiary sexual dysfunction involves "
            "psychological factors including depression, altered body image, and "
            "relationship stress. Treatment approaches include PDE5 inhibitors for "
            "erectile dysfunction, intracavernosal alprostadil injections, "
            "lubricants, and management of underlying MS symptoms. Neuroplasticity "
            "and rehabilitation strategies can improve sexual function in some "
            "patients with stable disease."
        ),
    },
    {
        "id": "med-009",
        "title": "Bupropion: Atypical Antidepressant Profile",
        "topic": "pharmacy",
        "content": (
            "Bupropion is an atypical antidepressant that acts primarily as a "
            "norepinephrine-dopamine reuptake inhibitor (NDRI), with minimal effect "
            "on serotonin reuptake. This unique mechanism distinguishes it from SSRIs "
            "and accounts for its favorable sexual side-effect profile. Bupropion is "
            "FDA-approved for major depressive disorder, seasonal affective disorder, "
            "and smoking cessation (as Zyban). It is often used as augmentation "
            "therapy for SSRI-treated patients experiencing sexual dysfunction, as "
            "its pro-dopaminergic action can counteract serotonin-mediated sexual "
            "inhibition. Bupropion may improve libido, arousal, and orgasmic function. "
            "The drug is available in immediate-release, sustained-release (SR), and "
            "extended-release (XL) formulations. Key contraindications include seizure "
            "disorders (bupropion lowers the seizure threshold), eating disorders, and "
            "concurrent use of monoamine oxidase inhibitors. Common side effects "
            "include dry mouth, insomnia, headache, and agitation, but notably not "
            "the weight gain or sexual dysfunction typical of SSRIs."
        ),
    },
    {
        "id": "med-010",
        "title": "Neuroplasticity and Pharmacological Intervention",
        "topic": "neurology / pharmacy",
        "content": (
            "Neuroplasticity refers to the brain's capacity to reorganize its "
            "structure and function in response to experience, learning, and injury. "
            "Brain-derived neurotrophic factor (BDNF) is a key mediator of synaptic "
            "plasticity, promoting neuronal survival, dendritic growth, and long-term "
            "potentiation in the hippocampus and prefrontal cortex. Chronic stress "
            "and depression are associated with reduced BDNF levels and hippocampal "
            "atrophy. Antidepressants, including SSRIs and ketamine, exert "
            "neuroplastic effects: SSRIs gradually upregulate BDNF expression over "
            "weeks (explaining the therapeutic lag), while ketamine produces rapid "
            "antidepressant effects via NMDA receptor antagonism and subsequent AMPA "
            "receptor activation, triggering a burst of BDNF-dependent synaptogenesis. "
            "Psilocybin, a serotonin 5-HT2A receptor agonist, promotes neural "
            "plasticity and is being investigated for treatment-resistant depression. "
            "Exercise is a potent non-pharmacological inducer of BDNF and "
            "neuroplasticity. Understanding these mechanisms informs rational "
            "polypharmacy strategies combining established and novel agents."
        ),
    },
]
