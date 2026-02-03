FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ARG VITE_CLERK_PUBLISHABLE_KEY=""
ARG VITE_GSD_API_BASE_URL=""
ARG VITE_GSD_CLERK_JWT_TEMPLATE="gsd"

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
