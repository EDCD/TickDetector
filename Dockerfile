FROM node:18-bullseye
EXPOSE 9001
WORKDIR /app
RUN chown -R node:node /app
COPY --chown=node:node package*.json ./
ENV NODE_ENV=development
RUN apt-get update -qq && apt-get install -qy \
    ca-certificates \
    bzip2 \
    curl \
    libfontconfig \
    --no-install-recommends
USER node
RUN npm config list
RUN npm ci \
    && npm cache clean --force
ENV PATH=/app/node_modules/.bin:$PATH
COPY --chown=node:node . .
ENV NODE_ENV=production
