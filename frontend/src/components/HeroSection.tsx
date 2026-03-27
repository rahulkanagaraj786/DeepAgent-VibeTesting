import { Link } from "react-router-dom";
import { ArrowRight, ExternalLink } from "lucide-react";
import { motion } from "framer-motion";

const HeroSection = () => {
  return (
    <section className="relative min-h-screen flex items-center justify-center pt-16 overflow-hidden surface-glow">
      {/* Subtle grid */}
      <div className="absolute inset-0 opacity-[0.04]" style={{
        backgroundImage: `linear-gradient(hsl(260 60% 50%) 1px, transparent 1px), linear-gradient(90deg, hsl(260 60% 50%) 1px, transparent 1px)`,
        backgroundSize: '60px 60px'
      }} />

      <div className="container relative z-10 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/50 px-4 py-1.5 text-sm text-muted-foreground mb-8"
        >
          <span className="text-primary">⚡</span>
          Deep Agents Hackathon · <span className="text-primary font-medium">TrueFoundry + Aerospike</span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="text-5xl sm:text-6xl lg:text-7xl font-bold leading-[1.1] mb-6"
        >
          Autonomous AI QA
          <br />
          <span className="text-gradient">for any GitHub repo</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mx-auto max-w-2xl text-lg text-muted-foreground mb-10"
        >
          Paste a repo URL. Vibe Testing clones it, infers the API spec, generates an MCP server,
          deploys it, then stress-tests it with a deep reasoning AI agent — zero manual setup.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <Link
            to="/pipeline"
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-8 py-3.5 text-base font-semibold text-primary-foreground hover:bg-primary/90 transition-all shadow-lg shadow-primary/20"
          >
            Start Testing
            <ExternalLink className="h-4 w-4" />
          </Link>
          <a
            href="#features"
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-secondary/50 px-8 py-3.5 text-base font-medium text-foreground hover:bg-secondary transition-all"
          >
            See How It Works
            <ArrowRight className="h-4 w-4" />
          </a>
        </motion.div>

        {/* Terminal preview */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.5 }}
          className="mt-16 mx-auto max-w-2xl"
        >
          <div className="rounded-xl border border-border bg-card overflow-hidden shadow-2xl glow-border">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
              <div className="h-3 w-3 rounded-full bg-destructive/60" />
              <div className="h-3 w-3 rounded-full bg-warning/60" />
              <div className="h-3 w-3 rounded-full bg-success/60" />
              <span className="ml-3 text-xs text-muted-foreground font-mono">vibe-testing — deep agents</span>
            </div>
            <div className="p-6 text-left font-mono text-sm space-y-2">
              <div className="text-muted-foreground">$ vibe-test run --url https://github.com/org/repo</div>
              <div className="flex items-center gap-2"><span className="text-success">✓</span> <span className="text-foreground/80">Cloning repository...</span> <span className="text-muted-foreground">depth=1</span></div>
              <div className="flex items-center gap-2"><span className="text-success">✓</span> <span className="text-foreground/80">Inferring API spec...</span> <span className="text-muted-foreground">FastAPI detected, 12 routes</span></div>
              <div className="flex items-center gap-2"><span className="text-success">✓</span> <span className="text-foreground/80">Mining capabilities...</span> <span className="text-muted-foreground">8 tools discovered</span></div>
              <div className="flex items-center gap-2"><span className="text-success">✓</span> <span className="text-foreground/80">Generating MCP server...</span> <span className="text-muted-foreground">DeepSeek-V3</span></div>
              <div className="flex items-center gap-2"><span className="text-success">✓</span> <span className="text-foreground/80">Deploying to TrueFoundry...</span> <span className="text-muted-foreground">live</span></div>
              <div className="flex items-center gap-2"><span className="text-success">✓</span> <span className="text-foreground/80">Orchestrator planning...</span> <span className="text-muted-foreground">fintech app, 3 risk flows</span></div>
              <div className="flex items-center gap-2"><span className="text-primary">→</span> <span className="text-foreground/80">Deep reasoning loop...</span> <span className="text-primary font-semibold">2 critical bugs + fixes</span></div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default HeroSection;
