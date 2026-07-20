
import { GoogleGenAI, Type, Schema } from "@google/genai";
import { TaskType } from "../types";

const apiKey = process.env.API_KEY || '';
const ai = new GoogleGenAI({ apiKey });

interface GeneratedQuest {
  title: string;
  description: string;
  loreSnippet: string;
  xpReward: number;
  type: TaskType;
  reminderMessage?: string;
}

export const generateQuestSuggestion = async (
  topic: string,
  childLevel: number,
  narrativeContext: string
): Promise<GeneratedQuest | null> => {
  if (!apiKey) {
    console.error("API Key missing");
    return null;
  }

  const prompt = `
    You are a Dungeon Master for a gamified productivity app for kids.
    Create a quest based on the real-world task: "${topic}".
    
    IMPORTANT CONTEXT / CURRENT SEASON THEME:
    "${narrativeContext}"
    (All lore and descriptions MUST fit this theme strictly. e.g., if the theme is "Ice Giants", a math task should involve calculating ice block weight or catapult angles against giants.)

    The child adventurer is Level ${childLevel}.
    
    The output must be a JSON object containing:
    - title: A creative, RPG-style name for the task fitting the theme.
    - description: Clear real-world instructions on what to do.
    - loreSnippet: A short, 1-sentence flavor text describing why this task helps the current story arc.
    - xpReward: A balanced integer experience point value (50-500).
    - type: The best fitting category from [DAILY, CHALLENGE, CHAIN, TIMED, COOP].
    - reminderMessage: A short, urgent, in-character sentence warning based on the theme (e.g. "The ice wall is cracking!", "The dragon is waking up!").
  `;

  const schema: Schema = {
    type: Type.OBJECT,
    properties: {
      title: { type: Type.STRING },
      description: { type: Type.STRING },
      loreSnippet: { type: Type.STRING },
      xpReward: { type: Type.INTEGER },
      type: { 
        type: Type.STRING, 
        enum: ["DAILY", "CHALLENGE", "CHAIN", "TIMED", "COOP"] 
      },
      reminderMessage: { type: Type.STRING },
    },
    required: ["title", "description", "loreSnippet", "xpReward", "type"],
  };

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-2.5-flash',
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseSchema: schema,
      },
    });

    if (response.text) {
      return JSON.parse(response.text) as GeneratedQuest;
    }
    return null;
  } catch (error) {
    console.error("Failed to generate quest:", error);
    return null;
  }
};

export const evaluateTaskProof = async (
  taskTitle: string,
  imageBase64: string // Expecting base64 string
): Promise<{ rating: number; comment: string } | null> => {
   if (!apiKey) return null;

   try {
     const response = await ai.models.generateContent({
       model: 'gemini-2.5-flash',
       contents: {
         parts: [
           { inlineData: { mimeType: 'image/jpeg', data: imageBase64.split(',')[1] } },
           { text: `I am a parent verifying a child's task: "${taskTitle}". Analyze this image. Give a rating from 1 to 5 stars based on quality/completeness (5 is perfect). Also provide a 1 sentence encouraging comment suitable for a child.` }
         ]
       },
       config: {
         responseMimeType: "application/json",
         responseSchema: {
           type: Type.OBJECT,
           properties: {
             rating: { type: Type.INTEGER },
             comment: { type: Type.STRING }
           },
           required: ["rating", "comment"]
         }
       }
     });

     if (response.text) {
       return JSON.parse(response.text);
     }
     return null;

   } catch (error) {
     console.error("Failed to analyze proof:", error);
     return { rating: 3, comment: "I couldn't clearly see the magic, but good effort!" };
   }
};
